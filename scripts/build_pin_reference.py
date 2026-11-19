"""Build data/reference/pincodes.csv (pin,office,district,state,city).

Sources, merged in order:
  1. Full India Post directory CSV(s) dropped into data/reference/raw/ (from data.gov.in).
  2. Seed PINs fetched from api.postalpincode.in (cached in data/reference/raw/api_cache.json).

Usage: python scripts/build_pin_reference.py [--no-api]
"""
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "data" / "reference"
RAW_DIR = REF_DIR / "raw"
CACHE = RAW_DIR / "api_cache.json"
OUT = REF_DIR / "pincodes.csv"

# Display city for each seed PIN; the demo generator draws customers from these.
SEED_PINS = {
    "Mumbai": ["400001", "400050", "400053", "400076", "400097"],
    "Pune": ["411001", "411004", "411038", "411057", "411014"],
    "Bengaluru": ["560001", "560034", "560066", "560095", "560076"],
    "Chennai": ["600001", "600017", "600040", "600096"],
    "Kolkata": ["700001", "700019", "700064"],
    "New Delhi": ["110001", "110017", "110085"],
    "Hyderabad": ["500001", "500032", "500081"],
    "Ahmedabad": ["380001", "380009", "380015"],
    "Jaipur": ["302001", "302017"],
    "Lucknow": ["226001", "226010"],
    "Kochi": ["682001", "682024"],
    "Chandigarh": ["160017", "160022"],
}

# Reference-only PINs: every one-digit insertion of the demo's broken PIN "40001",
# so the recovery candidate set is complete even without the full directory.
EXTRA_PINS = sorted({
    "40001"[:i] + d + "40001"[i:] for i in range(6) for d in "0123456789"
} - {p for pins in SEED_PINS.values() for p in pins})
EXTRA_PINS = [p for p in EXTRA_PINS if p[0] != "0"]

COLUMN_ALIASES = {
    "pin": ["pincode", "pin", "pin_code"],
    "office": ["officename", "office_name", "office"],
    "district": ["districtname", "district", "district_name"],
    "state": ["statename", "state", "state_name"],
}


def fetch_pin(pin: str, cache: dict) -> list[dict]:
    if pin in cache:
        return cache[pin]
    url = f"https://api.postalpincode.in/pincode/{pin}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)[0]
    except Exception as e:  # network trouble: skip, keep going
        print(f"  ! {pin}: {e}", file=sys.stderr)
        return []
    offices = [
        {"office": po["Name"], "district": po["District"], "state": po["State"]}
        for po in (data.get("PostOffice") or [])
    ]
    cache[pin] = offices
    time.sleep(0.2)
    return offices


def load_raw_directories() -> list[dict]:
    rows = []
    for path in sorted(RAW_DIR.glob("*.csv")):
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            lower = {h.lower().strip(): h for h in (reader.fieldnames or [])}
            cols = {}
            for key, options in COLUMN_ALIASES.items():
                cols[key] = next((lower[o] for o in options if o in lower), None)
            if not cols["pin"] or not cols["state"]:
                print(f"  skip {path.name}: no pincode/state columns ({reader.fieldnames})")
                continue
            for r in reader:
                pin = (r.get(cols["pin"]) or "").strip().split(".")[0]
                if len(pin) == 6 and pin.isdigit():
                    rows.append({
                        "pin": pin,
                        "office": (r.get(cols["office"]) or "").strip() if cols["office"] else "",
                        "district": (r.get(cols["district"]) or "").strip().title() if cols["district"] else "",
                        "state": (r.get(cols["state"]) or "").strip().title(),
                        "city": "",
                    })
        print(f"  loaded {path.name}: {len(rows)} rows so far")
    return rows


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_raw_directories()

    if "--no-api" not in sys.argv:
        cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        for city, pins in SEED_PINS.items():
            for pin in pins:
                for po in fetch_pin(pin, cache):
                    rows.append({"pin": pin, **po, "city": city})
        for pin in EXTRA_PINS:
            for po in fetch_pin(pin, cache):
                rows.append({"pin": pin, **po, "city": ""})
        CACHE.write_text(json.dumps(cache, indent=1))

    seed_city = {pin: city for city, pins in SEED_PINS.items() for pin in pins}
    seen, out = set(), []
    for r in rows:
        r["city"] = r["city"] or seed_city.get(r["pin"], "")
        key = (r["pin"], r["office"].lower())
        if key not in seen:
            seen.add(key)
            out.append(r)
    out.sort(key=lambda r: (r["pin"], r["office"]))

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pin", "office", "district", "state", "city"])
        w.writeheader()
        w.writerows(out)
    pins = {r["pin"] for r in out}
    missing = [p for p in seed_city if p not in pins]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} offices, {len(pins)} PINs")
    if missing:
        print(f"seed PINs not found: {missing}")


if __name__ == "__main__":
    main()
