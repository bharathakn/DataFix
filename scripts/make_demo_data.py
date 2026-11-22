"""Seeded demo data generator (see docs/09_DEMO_AND_PITCH.md §1).

Writes to data/demo/:
  customers_clean.csv   ground truth, 10,000 rows
  customers_dirty.csv   with injected errors + 200 duplicate rows (10,200 rows)
  orders.csv            linked table (dirty: total mismatches, conflicting phones for the refusal story)
  truth.json            every injected error

Run: cd backend && uv run python ../scripts/make_demo_data.py
App demo (what "Load demo dataset" opens): ... make_demo_data.py --rows 1000 --out data/demo_small
Scale test: ... make_demo_data.py --rows 100000 --out data/demo/scale_100k  (error counts scale with rows)

Story rows (the demo narrative) sit at fixed indices. Files below 4,000 rows use a compact set inside the first
1,000 rows; 10,000+ rows keep the original indices, so data/demo stays byte-identical.
"""
import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "demo"
API_CACHE = ROOT / "data" / "reference" / "raw" / "api_cache.json"
SEED = 42
N = 10_000
SCALE = 1.0  # error counts scale with N / 10,000 (set by --rows)
rng = random.Random(SEED)

# ---------------------------------------------------------------- vocab
MALE = ["Rahul", "Arjun", "Vikram", "Rohan", "Aditya", "Karan", "Siddharth", "Amit", "Suresh", "Rajesh",
        "Mohammad", "Imran", "Farhan", "Anil", "Sanjay", "Nikhil", "Varun", "Pranav", "Harish", "Deepak",
        "Manoj", "Ganesh", "Kiran", "Abhishek", "Yash", "Tushar", "Naveen", "Ravi", "Sunil", "Gaurav"]
FEMALE = ["Priya", "Sneha", "Ananya", "Pooja", "Kavya", "Divya", "Neha", "Aishwarya", "Meera", "Lakshmi",
          "Fatima", "Ayesha", "Shreya", "Ritu", "Swati", "Nandini", "Deepika", "Anjali", "Bhavna", "Isha",
          "Sunita", "Rekha", "Pallavi", "Shalini", "Tanvi", "Aditi", "Riya", "Komal", "Simran", "Jyoti"]
LAST = ["Sharma", "Verma", "Patel", "Reddy", "Iyer", "Nair", "Gupta", "Singh", "Kumar", "Joshi",
        "Kulkarni", "Deshpande", "Rao", "Menon", "Chatterjee", "Banerjee", "Das", "Khan", "Shaikh", "Mehta",
        "Shah", "Agarwal", "Pillai", "Naidu", "Bhat", "Hegde", "Mishra", "Pandey", "Yadav", "Chopra"]
APOS_LAST = ["D’Souza", "D’Costa", "D’Mello", "D’Cruz"]
DOMAINS = ["gmail.com"] * 5 + ["yahoo.com"] * 2 + ["outlook.com"] * 2 + ["rediffmail.com"]
OCCUPATIONS = {  # (weight, age range)
    "student": (12, (18, 24)), "software engineer": (20, (23, 45)), "teacher": (12, (28, 60)),
    "doctor": (6, (30, 65)), "shop owner": (14, (25, 65)), "accountant": (12, (24, 58)),
    "nurse": (8, (22, 55)), "retired": (10, (60, 80)),
}
CITY_WEIGHTS = {"Mumbai": 14, "Pune": 12, "Bengaluru": 14, "Chennai": 9, "Kolkata": 8, "New Delhi": 10,
                "Hyderabad": 9, "Ahmedabad": 7, "Jaipur": 5, "Lucknow": 5, "Kochi": 4, "Chandigarh": 3}
SOURCES = {"web_form": 40, "mobile_app": 25, "branch_upload": 20, "partner_api": 15}
NOTES = ["", "", "", "", "Prefers email contact", "Called support twice", "Interested in premium plan",
         "Referred by a friend", "Asked for invoice copy", "Delivery to office address", "VIP customer",
         "Requested callback in evening", "Moved recently"]

MISSPELL = {"Bengaluru": ["Banglore", "Bengaluru ", "Bengluru"], "Pune": ["Pune.", "Puna", "pune"],
            "Hyderabad": ["Hydrabad", "Hyderbad"], "Chennai": ["Chenai", "Chennnai"],
            "Mumbai": ["Mumbay", "Mumabi"], "Kolkata": ["Kolkatta", "Kolkta"], "Ahmedabad": ["Ahmadabad", "Ahemdabad"]}
ALIAS = {"Mumbai": "Bombay", "Bengaluru": "Bangalore", "Chennai": "Madras", "Kolkata": "Calcutta"}

# ---------------------------------------------------------------- validators used for generation
_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(num: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def aadhaar() -> str:
    base = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    a = base + verhoeff_check_digit(base)
    return f"{a[:4]} {a[4:8]} {a[8:]}"


def pan(last: str) -> str:
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    initial = next((ch for ch in last.upper() if ch.isalpha()), "X")
    return "".join(rng.choice(L) for _ in range(3)) + "P" + initial + f"{rng.randint(0, 9999):04d}" + rng.choice(L)


def wchoice(d: dict):
    return rng.choices(list(d), weights=[v if not isinstance(v, tuple) else v[0] for v in d.values()])[0]


def lakh_crore(v: int) -> str:
    style = rng.choice(["L", "indian", "cr"])
    if style == "L":
        return f"₹{v / 100000:g}L"
    if style == "cr":
        return f"{v / 10000000:g} Cr"
    s = str(v)
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


# ---------------------------------------------------------------- reference
def load_reference() -> dict:
    """Demo cities come from the cached India Post API answers for the seed PINs, not from pincodes.csv,
    so the demo stays byte-identical when the reference is rebuilt (e.g. with the full directory)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bpr", Path(__file__).with_name("build_pin_reference.py"))
    bpr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bpr)
    cache = json.loads(API_CACHE.read_text(encoding="utf-8"))
    rows, seen = [], set()
    for city, pins in bpr.SEED_PINS.items():
        for pin in pins:
            for po in cache.get(pin, []):
                if (pin, po["office"].lower()) not in seen:
                    seen.add((pin, po["office"].lower()))
                    rows.append({"pin": pin, "office": po["office"].strip(), "district": po["district"].strip(),
                                 "state": po["state"].strip(), "city": city})
    rows.sort(key=lambda r: (r["pin"], r["office"]))
    by_city: dict[str, list[dict]] = {}
    for r in rows:
        by_city.setdefault(r["city"], []).append(r)
    return by_city


# ---------------------------------------------------------------- build clean customers
def build_clean(by_city: dict) -> list[dict]:
    start, end = date(2022, 1, 1), date(2026, 10, 31)
    span = (end - start).days
    used_phones, used_emails = set(), set()
    rows = []
    for i in range(N):
        gender = rng.choice("MF")
        first = rng.choice(MALE if gender == "M" else FEMALE)
        last = rng.choice(APOS_LAST) if rng.random() < 0.02 else rng.choice(LAST)
        occ = wchoice(OCCUPATIONS)
        lo, hi = OCCUPATIONS[occ][1]
        city = wchoice(CITY_WEIGHTS)
        ref = rng.choice(by_city[city])
        email_local = f"{first}.{last}".lower().replace("’", "")
        while True:
            email = f"{email_local}{rng.randint(1, 999)}@{rng.choice(DOMAINS)}"
            if email not in used_emails:
                used_emails.add(email)
                break
        while True:
            phone = str(rng.randint(6, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(9))
            if phone not in used_phones:
                used_phones.add(phone)
                break
        signup = start + timedelta(days=rng.randint(0, span))
        income = int(round(rng.lognormvariate(13.3, 0.45), -4))
        rows.append({
            "customer_id": f"C-{10001 + i}",
            "name": f"{first} {last}",
            "gender": gender,
            "age": str(rng.randint(lo, hi)),
            "occupation": occ,
            "email": email,
            "phone": phone,
            "locality": ref["office"],
            "pin": ref["pin"],
            "city": city,
            "district": ref["district"],
            "state": ref["state"],
            "signup_date": signup.strftime("%d/%m/%Y"),
            "annual_income": str(min(max(income, 120000), 3500000)),
            "pan": "",
            "source": wchoice(SOURCES),
            "import_batch": "",
            "created_at": datetime.combine(signup, datetime.min.time()).replace(
                hour=rng.randint(8, 21), minute=rng.randint(0, 59)).isoformat(),
            "notes": rng.choice(NOTES),
        })
        rows[-1]["pan"] = pan(last) if rng.random() < 0.6 else ""
    # import batches: 12 equal date buckets
    order = sorted(range(N), key=lambda k: rows[k]["created_at"])
    for rank, k in enumerate(order):
        rows[k]["import_batch"] = f"B{rank * 12 // N + 1:02d}"
    return rows


def build_orders(customers: list[dict]) -> list[dict]:
    orders = []
    for c in customers:
        signup = datetime.strptime(c["signup_date"], "%d/%m/%Y").date()
        for _ in range(rng.choices([0, 1, 2, 3, 4, 5], weights=[8, 25, 25, 20, 12, 10])[0]):
            d = signup + timedelta(days=rng.randint(0, max(1, (date(2026, 11, 15) - signup).days)))
            qty = rng.randint(1, 5)
            price = rng.choice([199, 249, 499, 799, 999, 1299, 1999, 2499, 4999])
            orders.append({"order_id": "", "customer_id": c["customer_id"], "email": c["email"],
                           "phone": c["phone"], "order_date": d.strftime("%d/%m/%Y"),
                           "quantity": str(qty), "unit_price": str(price), "total": str(qty * price)})
    rng.shuffle(orders)
    orders.sort(key=lambda o: datetime.strptime(o["order_date"], "%d/%m/%Y"))
    for i, o in enumerate(orders):
        o["order_id"] = f"O-{500001 + i}"
    return orders


# ---------------------------------------------------------------- story rows
def story_rows() -> dict:
    """Index of each demo story row. The 10k demo keeps its historic rows; small demos keep 52/412/777 and move
    the rest inside the file."""
    if N >= 4000:
        return {"city": 52, "pin": 412, "phone_recover": 777, "phone_conflict": 1043, "age_impute": 2001,
                "age_small": (2002, 2003), "outliers": (3000, 3500, 4100, 5200, 6300)}
    return {"city": 52, "pin": 412, "phone_recover": 777, "phone_conflict": 643, "age_impute": 201,
            "age_small": (202, 203), "outliers": tuple(int(i * N / 10_000) for i in (3000, 3500, 4100, 5200, 6300))}


# ---------------------------------------------------------------- main
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_city = load_reference()
    clean = build_clean(by_city)

    # ---- story rows: clean-side setup (these define the truth)
    S = story_rows()
    R_CITY, R_PIN, R_REC, R_CONF, R_AGE = S["city"], S["pin"], S["phone_recover"], S["phone_conflict"], S["age_impute"]
    R_SMALL1, R_SMALL2 = S["age_small"]

    def set_clean(idx, **kv):
        clean[idx].update(kv)

    mumbai_400001 = next(r for r in by_city["Mumbai"] if r["pin"] == "400001" and r["office"] == "Stock Exchange")
    set_clean(R_PIN, city="Mumbai", pin="400001", locality=mumbai_400001["office"],
              district=mumbai_400001["district"], state="Maharashtra")
    blr = next(r for r in by_city["Bengaluru"] if r["pin"] == "560001")
    set_clean(R_CITY, city="Bengaluru", pin="560001", locality=blr["office"], district=blr["district"], state=blr["state"])
    pune = by_city["Pune"][0]
    set_clean(R_AGE, occupation="retired", age="68", city="Pune", pin=pune["pin"], locality=pune["office"],
              district=pune["district"], state=pune["state"])
    set_clean(R_SMALL1, occupation="astronaut", age="41")
    set_clean(R_SMALL2, occupation="astronaut", age="38")
    outliers = dict(zip(S["outliers"], ("8000000", "4500000", "6200000", "5000000", "7500000")))
    for idx, v in outliers.items():
        set_clean(idx, annual_income=v)

    # planted PII in notes (present in clean and dirty — privacy, not quality)
    pii_truth = []
    story = {R_CITY, R_PIN, R_REC, R_CONF, R_AGE, R_SMALL1, R_SMALL2, *outliers}
    pool = [i for i in range(N) if i not in story]
    n_pii = max(10, round(50 * SCALE))  # 50 in the 10k demo: 25 Aadhaar, 15 PAN, 10 phone
    pii_rows = rng.sample(pool, n_pii)
    for k, idx in enumerate(pii_rows):
        if k < n_pii * 0.5:
            val, kind, text = aadhaar(), "aadhaar", "KYC verified, Aadhaar {}"
        elif k < n_pii * 0.8:
            val, kind, text = pan(clean[idx]["name"].split()[-1]), "pan", "PAN on file: {}"
        else:
            val, kind, text = clean[idx]["phone"], "phone", "Alternate number {} (wife)"
            val = str(rng.randint(6, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(9))
        clean[idx]["notes"] = text.format(val)
        pii_truth.append({"row_ref": clean[idx]["customer_id"], "column": "notes", "pii_type": kind, "value": val})

    orders = build_orders(clean)
    # the phone-recovery and phone-conflict story rows need orders
    def ensure_orders(cid, n):
        have = [o for o in orders if o["customer_id"] == cid]
        c = next(c for c in clean if c["customer_id"] == cid)
        for _ in range(n - len(have)):
            orders.append({"order_id": f"O-{900001 + len(orders)}", "customer_id": cid, "email": c["email"],
                           "phone": c["phone"], "order_date": "15/06/2026", "quantity": "1",
                           "unit_price": "999", "total": "999"})
    ensure_orders(clean[R_REC]["customer_id"], 2)
    ensure_orders(clean[R_CONF]["customer_id"], 3)

    # ---- dirty copy
    dirty = [dict(r) for r in clean]
    truth = []
    touched: set[tuple[int, str]] = set()

    def inject(idx, col, new, etype, **extra):
        touched.add((idx, col))
        truth.append({"customer_id": clean[idx]["customer_id"], "base_index": idx, "column": col,
                      "clean_value": clean[idx][col], "dirty_value": new, "error_type": etype, **extra})
        dirty[idx][col] = new

    # story rows: dirty side
    inject(R_PIN, "pin", "40001", "invalid_pin", story=f"row {R_PIN}")
    inject(R_CITY, "city", "Banglore", "misspelling", story=f"row {R_CITY}")
    inject(R_REC, "phone", clean[R_REC]["phone"][:5], "truncated_phone", story=f"row {R_REC} phone recovery")
    inject(R_CONF, "phone", "", "missing", story=f"row {R_CONF} refused: conflicting phones in orders")
    inject(R_AGE, "age", "", "missing", story=f"row {R_AGE} group-median imputation")
    inject(R_SMALL1, "age", "", "missing", story=f"row {R_SMALL1} refused: group too small")
    cid_1043 = clean[R_CONF]["customer_id"]
    conflict_phone = "9" + "".join(str(rng.randint(0, 9)) for _ in range(9))
    for o in [o for o in orders if o["customer_id"] == cid_1043][1:]:
        o["phone"] = conflict_phone

    rows_used_for_dups = set(rng.sample(pool, round(200 * SCALE)))
    free = [i for i in pool if i not in rows_used_for_dups]

    def pick(n, where=lambda r: True, col=None, at_least=0):
        """n scaled to the file size; at_least keeps a root-cause story above the diagnosis threshold
        (10 issues) in small demos without changing the 10k demo."""
        n = max(at_least, round(n * SCALE))
        cands = [i for i in free if where(dirty[i]) and (col is None or (i, col) not in touched)]
        return rng.sample(cands, n)

    # blank city: 71 from mobile_app B07 + 2 elsewhere (root-cause story)
    for i in pick(71, lambda r: r["source"] == "mobile_app" and r["import_batch"] == "B07", "city", at_least=12):
        inject(i, "city", "", "missing", root_cause="mobile_app B07 drops city")
    for i in pick(2, lambda r: not (r["source"] == "mobile_app" and r["import_batch"] == "B07"), "city"):
        inject(i, "city", "", "missing")
    for col, n in (("email", 150), ("age", 100), ("phone", 150)):
        for i in pick(n, col=col):
            inject(i, col, "", "missing")
    # disguised missing
    for i in pick(120, lambda r: r["source"] == "branch_upload", "phone"):
        inject(i, "phone", "9999999999", "disguised_missing", root_cause="branch form placeholder")
    for i in pick(20, col="phone"):
        inject(i, "phone", "9999999999", "disguised_missing")
    for i in pick(30, col="email"):
        inject(i, "email", "test@test.com", "disguised_missing")
    # city misspellings / aliases / pin-city violations
    for i in pick(149, lambda r: r["city"] in MISSPELL, "city"):
        inject(i, "city", rng.choice(MISSPELL[dirty[i]["city"]]), "misspelling")
    for i in pick(60, lambda r: r["city"] in ALIAS, "city"):
        inject(i, "city", ALIAS[dirty[i]["city"]], "alias")
    for i in pick(40, col="city"):
        other = rng.choice([c for c in CITY_WEIGHTS if c != dirty[i]["city"]])
        inject(i, "city", other, "fd_violation", note="city disagrees with PIN")
    # invalid emails
    for i in pick(100, lambda r: r["email"] not in ("",), "email"):
        e = dirty[i]["email"]
        local, dom = e.split("@")
        bad = rng.choice([f"{local}@{dom.replace('.', '', 1)}", f"{local}@@{dom}", f"{local} @{dom}", f"{local}{dom}"])
        inject(i, "email", bad, "invalid_email")
    # invalid ages
    for i in pick(50, col="age"):
        inject(i, "age", rng.choice(["-5", "0", "150", "999", "-1"]), "invalid_age")
    # partner_api writes US dates
    for i in pick(50, lambda r: r["source"] == "partner_api", "signup_date", at_least=10):
        d = datetime.strptime(dirty[i]["signup_date"], "%d/%m/%Y")
        inject(i, "signup_date", d.strftime("%m/%d/%Y"), "date_format", root_cause="partner_api US dates")
    # 5-digit PINs / phones
    for i in pick(30, col="pin"):
        p = dirty[i]["pin"]
        k = rng.randint(1, 5)
        inject(i, "pin", p[:k] + p[k + 1:], "invalid_pin")
    for i in pick(30, col="phone"):
        inject(i, "phone", dirty[i]["phone"][:5], "truncated_phone")
    # Excel scientific notation from branch uploads
    sci_rows = pick(40, lambda r: r["source"] == "branch_upload", "phone", at_least=10)
    lossless = round(len(sci_rows) * 15 / 40)  # the rest lost digits: DataFix must refuse those
    for n, (i) in enumerate(sci_rows):
        p = dirty[i]["phone"]
        sci = f"{p[0]}.{p[1:]}E+09" if n < lossless else f"{p[0]}.{p[1:6]}E+09"
        inject(i, "phone", sci, "excel_sci_notation", lossy=n >= lossless, root_cause="branch_upload via Excel")
    # encoding damage (partner_api)
    for i in pick(20, lambda r: r["source"] == "partner_api", "name"):
        first = dirty[i]["name"].split()[0]
        lname = rng.choice(APOS_LAST)
        clean[i]["name"] = f"{first} {lname}"
        dirty[i]["name"] = clean[i]["name"]
        inject(i, "name", clean[i]["name"].encode("utf-8").decode("latin-1", errors="replace"),
               "encoding", root_cause="partner_api UTF-8 read as Latin-1")
    # income unit mix
    for i in pick(200, col="annual_income"):
        v = int(round(int(dirty[i]["annual_income"]), -4))
        clean[i]["annual_income"] = str(v)
        inject(i, "annual_income", lakh_crore(v), "money_format")
    # whitespace / case noise in name
    for i in pick(60, col="name"):
        inject(i, "name", rng.choice([f" {dirty[i]['name']}", f"{dirty[i]['name']}  ", dirty[i]["name"].upper()]),
               "whitespace_case")

    # ---- duplicates: 120 exact (new id), 80 near
    dup_sources = sorted(rows_used_for_dups)
    final, dup_truth = [], []
    insert_after = {}
    next_id = 20001
    for k, src in enumerate(dup_sources):
        row = dict(dirty[src])
        row["customer_id"] = f"C-{next_id}"
        next_id += 1
        kind = "duplicate" if k < round(120 * SCALE) else "near_duplicate"
        if kind == "near_duplicate":
            change = rng.choice(["name", "email", "phone"])
            if change == "name":
                n = row["name"]
                j = rng.randint(1, len(n) - 2)
                row["name"] = n[:j] + n[j + 1:]
            elif change == "email":
                row["email"] = row["email"].upper()
            else:
                p = row["phone"]
                row["phone"] = f"+91 {p[:5]} {p[5:]}"
        # insert only after the last story row (row 6500 in the 10k demo) so story rows keep their exact indices
        target = rng.randint(max(src, int(0.65 * N), max(story) + 1), N - 1)
        insert_after.setdefault(target, []).append((row, kind, dirty[src]["customer_id"]))
    for i in range(N):
        final.append(dirty[i])
        for row, kind, of in insert_after.get(i, []):
            final.append(row)
            dup_truth.append({"customer_id": row["customer_id"], "duplicate_of": of, "error_type": kind})
    # give 20 near-duplicates an order (exercises foreign-key remap on merge)
    near = [d for d in dup_truth if d["error_type"] == "near_duplicate"][:max(5, round(20 * SCALE))]
    for d in near:
        src = next(c for c in final if c["customer_id"] == d["duplicate_of"])
        orders.append({"order_id": f"O-{950001 + len(orders)}", "customer_id": d["customer_id"],
                       "email": src["email"], "phone": src["phone"], "order_date": "02/09/2026",
                       "quantity": "2", "unit_price": "499", "total": "998"})

    # story rows must keep their positions in the dirty file
    pos = {r["customer_id"]: k for k, r in enumerate(final)}
    story_ids = {clean[i]["customer_id"]: i for i in (R_CITY, R_PIN, R_REC, R_CONF, R_AGE, R_SMALL1, S["outliers"][0])}

    # orders: total mismatches
    order_truth = []
    for o in rng.sample(orders, max(5, round(30 * SCALE))):
        good = o["total"]
        o["total"] = str(int(good) + rng.choice([-100, 100, 1000, -1, 10]))
        order_truth.append({"order_id": o["order_id"], "column": "total", "clean_value": good,
                            "dirty_value": o["total"], "error_type": "crossfield_total"})

    # ---- write
    cols = list(clean[0].keys())
    for name, data in (("customers_clean.csv", clean), ("customers_dirty.csv", final)):
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(data)
    with (OUT / "orders.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(orders[0].keys()))
        w.writeheader()
        w.writerows(orders)
    for t in truth:
        t["dirty_row"] = pos[t["customer_id"]]
    (OUT / "truth.json").write_text(json.dumps({
        "seed": SEED,
        "customers_cell_errors": truth,
        "customers_duplicates": dup_truth,
        "orders_errors": order_truth,
        "pii": pii_truth,
        "valid_outliers": [{"customer_id": clean[i]["customer_id"], "column": "annual_income", "value": v}
                           for i, v in outliers.items()],
        "story_rows": {cid: {"base_index": i, "dirty_row": pos[cid]} for cid, i in story_ids.items()},
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    print(f"customers_clean: {len(clean)}  customers_dirty: {len(final)}  orders: {len(orders)}")
    print("cell errors:", dict(Counter(t["error_type"] for t in truth)))
    print("duplicates:", dict(Counter(d["error_type"] for d in dup_truth)), " pii:", len(pii_truth))
    print("story rows (dirty row index):", {cid: pos[cid] for cid in story_ids})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=10_000)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    N, SCALE, OUT = a.rows, a.rows / 10_000, Path(a.out)
    if not OUT.is_absolute():
        OUT = ROOT / OUT
    main()
