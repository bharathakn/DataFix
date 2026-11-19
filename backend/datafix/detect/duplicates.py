"""Exact and near duplicates. Near duplicates use blocking so we never compare all row pairs."""
from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz

from .. import validators as v
from . import ScanContext

MAX_BLOCK = 50
NEAR_THRESHOLD = 92.0
SKIP_TYPES = {"text"}
# A different date, amount, ID or phone means a different record/event, never a typo of the same one.
STRICT_TYPES = {"date", "number", "money", "age", "pin", "phone", "id", "pan", "gstin", "aadhaar", "ifsc"}
MAX_DIFF_COLS = 2
MIN_FIELD_SIM = 85


def _identity_cols(ctx: ScanContext) -> list[str]:
    """Columns that describe the entity: drop unique IDs (a re-insert gets a new ID) and free text."""
    out = []
    for c, i in ctx.columns.items():
        if i.semantic_type == "id" and i.distinct >= 0.95 * len(ctx.df):
            continue
        if i.semantic_type in SKIP_TYPES:
            continue
        out.append(c)
    return out


def _norm(col_type: str, x: str) -> str:
    if col_type == "phone":
        return v.normalize_phone(x)
    return " ".join(x.casefold().split())


def _pair_score(cols, types, nl, i, j) -> float:
    sims, diff = [], 0
    for c in cols:
        a, b = nl[c][i], nl[c][j]
        if a == b:
            sims.append(100.0)
            continue
        if types[c] in STRICT_TYPES and a and b:
            return 0.0
        r = fuzz.ratio(a, b) if a and b else 0.0
        if a and b and r < MIN_FIELD_SIM:
            return 0.0
        diff += 1
        if diff > MAX_DIFF_COLS:
            return 0.0
        sims.append(r)
    return sum(sims) / len(sims)


def detect_duplicates(ctx: ScanContext) -> None:
    df = ctx.df
    cols = _identity_cols(ctx)
    if not cols:
        return
    # exact
    key = df[cols].agg("\x1f".join, axis=1)
    first_of: dict[str, int] = {}
    for r, k in key.items():
        first_of.setdefault(k, r)
    first = key.map(first_of)
    exact = key.duplicated(keep="first")
    for rid in exact[exact].index:
        ctx.add(rid, None, "duplicate", "duplicates:exact", f"row is an exact copy of row {first[rid]}",
                duplicate_of=int(first[rid]))
    exact_rows = set(exact[exact].index)

    # near: block on email / phone / name+pin
    types = {c: ctx.columns[c].semantic_type for c in cols}
    normed = {c: df[c].map(lambda x, t=types[c]: _norm(t, x)) for c in cols}
    nl = {c: normed[c].to_dict() for c in cols}  # by row label: repaired tables have gaps in the index
    blocks: list[pd.Series] = []
    for c in cols:
        if types[c] in ("email", "phone"):
            blocks.append(normed[c].where(ctx.usable(c), ""))
    name = next((c for c in cols if types[c] == "name"), None)
    pin = next((c for c in cols if types[c] == "pin"), None)
    if name and pin:
        blocks.append((normed[name].str[:3] + "|" + normed[pin]).where(ctx.usable(name) & ctx.usable(pin), ""))

    parent: dict[int, int] = {}

    def find(a):
        while parent.get(a, a) != a:
            a = parent[a]
        return a

    pairs: dict[tuple[int, int], float] = {}
    for b in blocks:
        b = b[b != ""]
        for _, idx in b.groupby(b).groups.items():
            if len(idx) < 2 or len(idx) > MAX_BLOCK:
                continue
            for i, j in combinations(sorted(idx), 2):
                if (i, j) in pairs or i in exact_rows or j in exact_rows:
                    continue
                score = _pair_score(cols, types, nl, i, j)
                pairs[(i, j)] = score
                if score >= NEAR_THRESHOLD:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[max(ri, rj)] = min(ri, rj)
    best: dict[int, float] = {}
    for (i, j), score in pairs.items():
        if score >= NEAR_THRESHOLD:
            best[j] = max(best.get(j, 0), score)
    for r in sorted(best):
        root = find(r)
        if r != root:
            ctx.add(r, None, "near_duplicate", "duplicates:near",
                    f"row looks like the same record as row {root} ({best[r]:.0f}% similar)",
                    duplicate_of=int(root), similarity=round(best[r], 1))
