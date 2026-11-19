"""Privacy shield (docs/06_AI_PRIVACY_SPEC.md §1): find PII with checksums, mask it four ways."""
import hashlib
import hmac
import re

import pandas as pd

from . import validators as v
from .coltypes import header_tokens
from .models import ColumnInfo

RISK = {"aadhaar": "high", "pan": "high", "card": "high", "bank_account": "high", "gstin": "medium",
        "phone": "medium", "email": "medium", "ifsc": "low"}
VALIDATED_BY = {"aadhaar": "Verhoeff checksum", "card": "Luhn checksum", "gstin": "GSTIN mod-36 check character",
                "pan": "PAN structure (entity-type letter)", "phone": "Indian mobile format",
                "email": "email format", "ifsc": "IFSC format", "bank_account": "column name + digit length"}
STRUCTURED = {"aadhaar", "pan", "gstin", "phone", "email", "ifsc"}

# free-text patterns, most specific first; each hit is confirmed by the validator
SPAN_PATTERNS = [
    ("aadhaar", re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"), v.is_aadhaar),
    ("card", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), v.is_card),
    ("pan", re.compile(r"\b[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z]\b"), v.is_pan),
    ("gstin", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"), v.is_gstin),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), v.is_email),
    ("phone", re.compile(r"(?<![\d+])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"), v.is_phone),
]


def find_spans(text: str) -> list[tuple[int, int, str, str]]:
    spans, taken = [], []
    for kind, rx, ok in SPAN_PATTERNS:
        for m in rx.finditer(text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken) or not ok(m.group()):
                continue
            spans.append((s, e, kind, m.group()))
            taken.append((s, e))
    return sorted(spans)


def _bank_column(col: str, s: pd.Series) -> bool:
    toks = set(header_tokens(col))
    if not toks & {"account", "acc", "acct", "accno"}:
        return False
    vals = s[s.str.strip() != ""].head(500)
    return len(vals) > 0 and vals.str.fullmatch(r"\d{9,18}").mean() > 0.8


def scan_pii(df: pd.DataFrame, columns: dict[str, ColumnInfo]) -> list[dict]:
    findings = []
    for col, info in columns.items():
        s = df[col]
        t = info.semantic_type
        if t in STRUCTURED:
            check = {"aadhaar": v.is_aadhaar, "pan": v.is_pan, "gstin": v.is_gstin, "phone": v.is_phone,
                     "email": v.is_email, "ifsc": v.is_ifsc}[t]
            rows = int(s.map(lambda x: bool(x.strip()) and check(x)).sum())
            if rows:
                sample = next(x for x in s if x.strip() and check(x))
                findings.append(_finding(col, t, rows, False, mask_value(sample, t, "partial")))
            continue
        if _bank_column(col, s):
            rows = int(s.str.fullmatch(r"\d{9,18}").sum())
            findings.append(_finding(col, "bank_account", rows, False, mask_value(s[s != ""].iloc[0], "bank_account", "partial")))
            continue
        if t in ("text", "unknown", "name", "category", "locality"):
            hits: dict[str, list[str]] = {}
            for x in s:
                if len(x) < 10 or not any(ch.isdigit() for ch in x) and "@" not in x:
                    continue
                for _, _, kind, val in find_spans(x):
                    hits.setdefault(kind, []).append(val)
            for kind, vals in hits.items():
                findings.append(_finding(col, kind, len(vals), True, mask_value(vals[0], kind, "partial")))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda f: (order[f["risk"]], -f["rows"]))


def _finding(col: str, kind: str, rows: int, free_text: bool, sample_masked: str) -> dict:
    return {"column": col, "pii_type": kind, "rows": rows, "in_free_text": free_text,
            "risk": "high" if free_text and RISK[kind] != "low" else RISK[kind],
            "validated_by": VALIDATED_BY[kind], "sample_masked": sample_masked, "masked": False, "method": None}


def mask_value(x: str, kind: str, method: str, salt: str = "") -> str:
    x = x.strip()
    if not x:
        return x
    if method == "redact":
        return f"[REDACTED-{kind.upper()}]"
    if method == "hash":
        key = v.normalize_phone(x) if kind == "phone" else re.sub(r"[\s-]", "", x).casefold()
        return "h_" + hmac.new(salt.encode(), key.encode(), hashlib.sha256).hexdigest()[:12]
    # partial: keep just enough to recognise the record
    if kind == "email" and "@" in x:
        local, dom = x.split("@", 1)
        return f"{local[:2]}***@{dom}"
    digits = re.sub(r"\D", "", x)
    if kind == "phone":
        d = v.normalize_phone(x)
        return f"{d[:2]}XXXXXX{d[-2:]}" if len(d) >= 4 else "X" * len(d)
    if kind == "aadhaar":
        return f"XXXX XXXX {digits[-4:]}"
    if kind in ("card", "bank_account"):
        return "X" * (len(digits) - 4) + digits[-4:]
    if kind == "pan":
        return x[:5] + "****" + x[-1:]
    if kind == "gstin":
        return x[:2] + "X" * 10 + x[-3:]
    return x[:2] + "X" * max(len(x) - 4, 0) + x[-2:]


def mask_text(text: str, method: str, salt: str = "", kinds: set[str] | None = None) -> str:
    out, last = [], 0
    for s, e, kind, val in find_spans(text):
        if kinds and kind not in kinds:
            continue
        out.append(text[last:s])
        out.append(mask_value(val, kind, method, salt))
        last = e
    out.append(text[last:])
    return "".join(out)
