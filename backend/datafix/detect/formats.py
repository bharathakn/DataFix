"""Invalid formats: a present value that fails its column's validator."""
import re

import pandas as pd

from .. import validators as v
from . import ScanContext


def _phone(x: str, ctx) -> tuple[bool, str]:
    if v.is_phone(x):
        return True, ""
    if v.is_sci_notation(x):
        return False, "excel_scientific_notation"
    digits = re.sub(r"\D", "", x)
    if len(digits) < 10:
        return False, "too_short"
    return False, "invalid_phone"


def _pin(x: str, ctx) -> tuple[bool, str]:
    x = x.strip()
    if not v.is_pin_format(x):
        return False, "wrong_length" if x.isdigit() else "not_a_pin"
    if ctx.ref is not None and x not in ctx.ref:
        return False, "not_in_india_post_directory"
    return True, ""


def _age(x: str, ctx) -> tuple[bool, str]:
    if v.is_age(x):
        return True, ""
    return False, "out_of_range" if re.fullmatch(r"-?\d+", x.strip()) else "not_a_number"


def _simple(fn, kind):
    return lambda x, ctx: (True, "") if fn(x) else (False, kind)


CHECKS = {
    "email": _simple(v.is_email, "invalid_email"),
    "phone": _phone,
    "pin": _pin,
    "age": _age,
    "date": _simple(lambda x: bool(v.date_families(x)), "unparseable_date"),
    "money": _simple(lambda x: v.parse_money(x) is not None, "unparseable_amount"),
    "number": _simple(v.is_number, "not_a_number"),
    "pan": _simple(v.is_pan, "invalid_pan"),
    "gstin": _simple(v.is_gstin, "invalid_gstin"),
    "aadhaar": _simple(v.is_aadhaar, "invalid_aadhaar"),
    "ifsc": _simple(v.is_ifsc, "invalid_ifsc"),
}

MESSAGES = {
    "excel_scientific_notation": "{col} was saved in scientific notation (Excel), digits may be lost",
    "too_short": "{col} has too few digits for a mobile number",
    "wrong_length": "{col} is not 6 digits",
    "not_in_india_post_directory": "{col} is not a PIN in the India Post directory",
    "out_of_range": "{col} is outside 1–120",
    "encoding": "{col} contains garbled characters (encoding damage)",
}


def detect_formats(ctx: ScanContext) -> None:
    for col, info in ctx.columns.items():
        s = ctx.df[col]
        usable = ~ctx.unusable[col]
        invalid = pd.Series(False, index=s.index)
        check = CHECKS.get(info.semantic_type)
        moji = s.str.contains(v.MOJIBAKE_RE) & usable
        cache: dict[str, tuple[bool, str]] = {}
        for rid, x in s[usable].items():
            if moji[rid]:
                res = (False, "encoding")
            elif check is None:
                continue
            else:
                res = cache.get(x)
                if res is None:
                    res = cache[x] = check(x, ctx)
            if not res[0]:
                invalid[rid] = True
                msg = MESSAGES.get(res[1], "{col} has an invalid format").format(col=col)
                ctx.add(rid, col, "invalid_format", f"format:{info.semantic_type}", msg, x, kind=res[1])
        ctx.invalid[col] = invalid
