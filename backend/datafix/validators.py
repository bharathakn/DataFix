"""Value-level validators and normalisers (docs/05_ENGINE_SPEC.md §9)."""
import re
from datetime import datetime
from functools import lru_cache

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")
PIN_RE = re.compile(r"^[1-9]\d{5}$")
PAN_RE = re.compile(r"^[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z]$")
GSTIN_RE = re.compile(r"^(0[1-9]|[1-3]\d)[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
SCI_RE = re.compile(r"^\d(?:\.\d+)?[eE]\+?\d+$")
# UTF-8 bytes misread as cp1252 ("â€™", "Ã©") or latin-1 (C1 control chars), plus U+FFFD
MOJIBAKE_RE = re.compile(r"Ã.|Â|â€|[\x80-\x9f]|\ufffd")
_PHONE_STRIP = re.compile(r"[\s\-().]")
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")

# ------------------------------------------------------------------ text


def norm_key(v: str) -> str:
    """Comparison key: casefold, drop punctuation, collapse whitespace."""
    v = re.sub(r"[^\w\s]", "", v.casefold())
    return " ".join(v.split())


_OFFICE_SUFFIX = re.compile(r"\s+(?:s\.?\s?o|b\.?\s?o|h\.?\s?o|g\.?\s?p\.?\s?o|e\.?\s?d\.?\s?o|po)\.?$", re.I)


def office_key(name: str) -> str:
    """'Stock Exchange SO' (India Post directory) == 'Stock Exchange' (API / user data)."""
    return norm_key(_OFFICE_SUFFIX.sub("", name.strip()))


def has_mojibake(v: str) -> bool:
    return bool(MOJIBAKE_RE.search(v))


def is_number(v: str) -> bool:
    return bool(_NUMBER_RE.match(v.strip()))


# ------------------------------------------------------------------ contact


def is_email(v: str) -> bool:
    return bool(EMAIL_RE.match(v.strip()))


def normalize_phone(v: str) -> str:
    s = _PHONE_STRIP.sub("", v.strip())
    if s.startswith("+91"):
        s = s[3:]
    elif s.startswith("0091"):
        s = s[4:]
    elif len(s) == 12 and s.startswith("91"):
        s = s[2:]
    elif len(s) == 11 and s.startswith("0"):
        s = s[1:]
    return s


def is_phone(v: str) -> bool:
    return bool(PHONE_RE.match(normalize_phone(v)))


def is_sci_notation(v: str) -> bool:
    return bool(SCI_RE.match(v.strip()))


# ------------------------------------------------------------------ Indian identifiers

_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
       [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
       [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
       [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
       [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
       [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0


def luhn_ok(num: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def is_aadhaar(v: str) -> bool:
    d = re.sub(r"[\s-]", "", v)
    return bool(re.fullmatch(r"[2-9]\d{11}", d)) and verhoeff_ok(d)


def is_card(v: str) -> bool:
    d = re.sub(r"[\s-]", "", v)
    return bool(re.fullmatch(r"\d{13,19}", d)) and luhn_ok(d)


def is_pan(v: str) -> bool:
    return bool(PAN_RE.match(v.strip()))


_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        p = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += p // 36 + p % 36
    return _GST_CHARS[(36 - total % 36) % 36]


def is_gstin(v: str) -> bool:
    v = v.strip()
    return bool(GSTIN_RE.match(v)) and gstin_check_char(v[:14]) == v[14]


def is_ifsc(v: str) -> bool:
    return bool(IFSC_RE.match(v.strip()))


def is_pin_format(v: str) -> bool:
    return bool(PIN_RE.match(v.strip()))


# ------------------------------------------------------------------ numbers


def is_age(v: str) -> bool:
    v = v.strip()
    return v.isdigit() and 1 <= int(v) <= 120


_MONEY_RE = re.compile(
    r"^(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(l|lac|lacs|lakh|lakhs|cr|crore|crores|k|m|mn)?\.?$", re.I)
_MULT = {"l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5, "cr": 1e7, "crore": 1e7, "crores": 1e7,
         "k": 1e3, "m": 1e6, "mn": 1e6}


def parse_money(v: str) -> float | None:
    m = _MONEY_RE.match(v.strip())
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        value = float(num)
    except ValueError:
        return None
    return value * _MULT.get((m.group(2) or "").lower(), 1)


def money_style(v: str) -> str:
    """Representation class used to spot mixed formats within one column."""
    s = v.strip().lower()
    if re.search(r"(cr|crore|crores)\.?$", s):
        return "crore"
    if re.search(r"(l|lac|lacs|lakh|lakhs)\.?$", s):
        return "lakh"
    if re.search(r"(k|m|mn)\.?$", s):
        return "short"
    if s.startswith(("₹", "rs", "inr")):
        return "symbol"
    if "," in s:
        return "commas"
    return "plain"


# ------------------------------------------------------------------ dates

DATE_FORMATS = {
    "%d/%m/%Y": "dmy", "%d-%m-%Y": "dmy", "%d.%m.%Y": "dmy", "%d/%m/%y": "dmy",
    "%m/%d/%Y": "mdy", "%m-%d-%Y": "mdy",
    "%Y-%m-%d": "iso", "%Y/%m/%d": "iso", "%Y-%m-%dT%H:%M:%S": "iso", "%Y-%m-%dT%H:%M": "iso",
    "%Y-%m-%d %H:%M:%S": "iso", "%Y-%m-%d %H:%M": "iso", "%Y-%m-%dT%H:%M:%S.%f": "iso",
    "%d %b %Y": "text", "%d-%b-%Y": "text", "%b %d, %Y": "text", "%d %B %Y": "text", "%B %d, %Y": "text",
}
_HAS_DIGIT = re.compile(r"\d")


@lru_cache(maxsize=300_000)
def date_families(v: str) -> frozenset[str]:
    """Families ('dmy', 'mdy', 'iso', 'text') under which the value parses as a real date."""
    v = v.strip()
    if not v or len(v) > 32 or not _HAS_DIGIT.search(v):
        return frozenset()
    fams = set()
    for fmt, fam in DATE_FORMATS.items():
        if fam in fams:
            continue
        try:
            d = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if 1900 <= d.year <= 2100:
            fams.add(fam)
    return frozenset(fams)


def parse_date_exact(v: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(v.strip(), fmt)
    except ValueError:
        return None


def parse_date(v: str, prefer: str | None = None) -> datetime | None:
    v = v.strip()
    fmts = sorted(DATE_FORMATS, key=lambda f: DATE_FORMATS[f] != prefer)
    for fmt in fmts:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None
