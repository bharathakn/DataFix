"""Semantic column type detection from values + header hints (docs/05_ENGINE_SPEC.md §3)."""
import re

import pandas as pd

from . import validators as v
from .knowledge import DISGUISED_TOKENS
from .models import ColumnInfo
from .reference import PinReference

# Tie-break order: more specific types first.
TYPE_ORDER = ["aadhaar", "pan", "gstin", "ifsc", "email", "phone", "pin", "date", "age", "money", "city", "state",
              "district", "locality", "name", "id", "text", "number", "category"]

HINTS = {
    "email": {"email", "mail", "emailid"},
    "phone": {"phone", "mobile", "contact", "cell", "tel", "telephone", "whatsapp", "mob"},
    "pin": {"pin", "pincode", "zip", "zipcode", "postal", "postcode"},
    "date": {"date", "dob", "time", "timestamp", "day", "dt"},
    "age": {"age"},
    "money": {"income", "salary", "amount", "price", "total", "cost", "revenue", "fee", "fees", "balance", "ctc",
              "amt", "value", "mrp", "payment"},
    "pan": {"pan"}, "gstin": {"gst", "gstin"}, "aadhaar": {"aadhaar", "aadhar", "uid"}, "ifsc": {"ifsc"},
    "city": {"city", "town"}, "state": {"state"}, "district": {"district"},
    "locality": {"locality", "area", "locality_name", "neighbourhood", "neighborhood", "suburb"},
    "name": {"name", "fullname", "customer", "person"},
    "text": {"note", "notes", "comment", "comments", "remark", "remarks", "description", "address", "feedback"},
    "id": {"id", "code", "no", "key", "uuid", "ref"},
}
_ALPHA = re.compile(r"^[^\d@]+$")


def header_tokens(header: str) -> list[str]:
    h = re.sub(r"([a-z])([A-Z])", r"\1_\2", header)
    return [t for t in re.split(r"[^a-z0-9]+", h.lower()) if t]


def _hint(t: str, toks: list[str], header: str) -> bool:
    if t == "id":
        return bool(toks) and toks[-1] in HINTS["id"]
    if t == "date" and header.lower().endswith(("_at", "_on")):
        return True
    return any(tok in HINTS.get(t, ()) for tok in toks)


def _ratio(values: list[str], fn) -> float:
    return sum(1 for x in values if fn(x)) / len(values) if values else 0.0


def infer_column(name: str, s: pd.Series, ref: PinReference | None = None) -> ColumnInfo:
    stripped = s.str.strip()
    nonblank = stripped[stripped != ""]
    null_count = int(len(s) - len(nonblank))
    distinct = int(nonblank.nunique())
    usable = nonblank[~nonblank.str.casefold().isin(DISGUISED_TOKENS)]
    sample_series = usable.sample(2000, random_state=42) if len(usable) > 2000 else usable
    vals = sample_series.tolist()
    info = ColumnInfo(name, "unknown", 0.0, null_count, distinct, nonblank.head(5).tolist())
    if not vals:
        return info

    toks = header_tokens(name)
    distinct_ratio = distinct / max(len(nonblank), 1)
    avg_len = sum(len(x) for x in vals) / len(vals)
    in_ref = (lambda x: x in ref) if ref else (lambda x: True)

    strict = {
        "aadhaar": v.is_aadhaar, "pan": v.is_pan, "gstin": v.is_gstin, "ifsc": v.is_ifsc,
        "email": v.is_email, "phone": v.is_phone,
        "pin": lambda x: v.is_pin_format(x) and in_ref(x),
        "date": lambda x: bool(v.date_families(x)),
        "age": v.is_age, "money": lambda x: v.parse_money(x) is not None, "number": v.is_number,
    }
    lenient = {
        "email": lambda x: "@" in x,
        "phone": lambda x: v.is_sci_notation(x) or re.fullmatch(r"\+?[\d\s\-()]{5,16}", x) is not None,
        "pin": lambda x: re.fullmatch(r"\d{5,7}", x) is not None,
        "aadhaar": lambda x: re.fullmatch(r"[\d\s-]{12,14}", x) is not None,
        "pan": lambda x: re.fullmatch(r"[A-Za-z0-9]{9,11}", x) is not None,
        "gstin": lambda x: re.fullmatch(r"[A-Za-z0-9]{14,16}", x) is not None,
        "ifsc": lambda x: re.fullmatch(r"[A-Za-z0-9]{10,12}", x) is not None,
        "age": lambda x: re.fullmatch(r"-?\d{1,3}", x) is not None,
    }

    scores: dict[str, float] = {}
    for t in TYPE_ORDER:
        hinted = _hint(t, toks, name)
        if t in strict:
            if t == "age" and not hinted:
                continue
            score = _ratio(vals, strict[t])
            if t == "money" and not hinted:
                marked = _ratio(vals, lambda x: v.money_style(x) not in ("plain",))
                if marked < 0.2:
                    continue
            if hinted:
                score = max(score, _ratio(vals, lenient.get(t, strict[t]))) + 0.15
            if t == "number":
                score *= 0.9  # generic: any specific type that fits should win
        elif t in ("city", "state", "district", "locality", "name"):
            if not hinted:
                continue
            score = _ratio(vals, lambda x: bool(_ALPHA.match(x))) + 0.15
        elif t == "text":
            score = 1.0 if hinted else (0.7 if avg_len > 30 else 0.0)
        elif t == "id":
            no_space = _ratio(vals, lambda x: " " not in x.strip() and len(x) <= 40)
            if hinted:
                score = no_space + 0.15
            elif distinct_ratio >= 0.98 and avg_len <= 20:
                score = 0.62 * no_space
            else:
                continue
        elif t == "category":
            score = 0.61 if (distinct <= 50 or distinct_ratio < 0.05) else 0.0
        else:
            continue
        scores[t] = score

    best = max(scores, key=lambda t: (round(scores[t], 4), -TYPE_ORDER.index(t)), default=None)
    if best and scores[best] >= 0.6:
        info.semantic_type, info.type_confidence = best, round(min(scores[best], 1.0), 3)
    return info


def infer_columns(df: pd.DataFrame, ref: PinReference | None = None,
                  overrides: dict[str, str] | None = None) -> dict[str, ColumnInfo]:
    cols = {c: infer_column(c, df[c], ref) for c in df.columns}
    for c, t in (overrides or {}).items():
        if c in cols:
            cols[c].semantic_type, cols[c].type_confidence, cols[c].overridden = t, 1.0, True
    return cols
