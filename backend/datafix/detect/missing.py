"""Missing values, disguised placeholders and sparse (optional-by-design) columns."""
import re

import pandas as pd

from ..knowledge import DISGUISED_TOKENS
from . import ScanContext

SPARSE_RATIO = 0.30  # a column this empty is optional by design; don't flag each blank cell
_REPEATED_DIGIT = re.compile(r"^(\d)\1{5,}$")
_NUMERIC_TYPES = {"phone", "pin", "aadhaar", "id", "number"}


def detect_missing(ctx: ScanContext) -> None:
    for col, info in ctx.columns.items():
        s = ctx.df[col]
        stripped = s.str.strip()
        blank = stripped == ""
        disguised, reasons = _disguised(stripped, blank, info.semantic_type)
        ctx.blank[col] = blank
        ctx.unusable[col] = blank | disguised

        if blank.mean() >= SPARSE_RATIO:
            ctx.sparse.add(col)
            ctx.add(None, col, "sparse_column", "missing",
                    f"{col} is empty in {blank.mean():.0%} of rows; treated as optional", blank_rows=int(blank.sum()))
        else:
            for rid in blank[blank].index:
                ctx.add(rid, col, "missing", "missing", f"{col} is empty", s[rid])
        for rid in disguised[disguised].index:
            ctx.add(rid, col, "disguised_missing", "disguised", f"{col} holds a placeholder instead of a value",
                    s[rid], reason=reasons[rid])


def _disguised(stripped: pd.Series, blank: pd.Series, semantic_type: str) -> tuple[pd.Series, dict]:
    folded = stripped.str.casefold()
    mask = folded.isin(DISGUISED_TOKENS) & ~blank
    reasons = {rid: "placeholder token" for rid in mask[mask].index}

    if semantic_type in _NUMERIC_TYPES:
        rep = stripped.str.match(_REPEATED_DIGIT) & ~blank & ~mask
        mask |= rep
        reasons.update({rid: "repeated digit placeholder" for rid in rep[rep].index})

    nonblank = stripped[~blank]
    if len(nonblank) >= 100 and nonblank.nunique() / len(nonblank) > 0.5:
        counts = nonblank.value_counts()
        limit = max(10, 20 * counts.median())
        spikes = set(counts[counts > limit].index)
        if spikes:
            spike = stripped.isin(spikes) & ~blank & ~mask
            mask |= spike
            for rid in spike[spike].index:
                reasons[rid] = f"frequency spike: appears {counts[stripped[rid]]} times in a mostly-unique column"
    return mask, reasons
