"""Inconsistent representations: whitespace, case, variants, aliases, spelling, mixed date/money formats.

Also builds ctx.canonical[col] (raw -> canonical value) so later detectors (FD) see one value per entity.
"""
from collections import Counter

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import OSA

from .. import validators as v
from ..knowledge import CITY_ALIASES
from . import CATEGORY_LIKE, ScanContext

_NO_WHITESPACE_CHECK = {"text"}


def detect_consistency(ctx: ScanContext) -> None:
    for col, info in ctx.columns.items():
        t = info.semantic_type
        s = ctx.df[col]
        usable = ctx.usable(col)
        if t not in _NO_WHITESPACE_CHECK:
            _whitespace(ctx, col, s, usable)
        if t in ("name", "city"):
            _case(ctx, col, s, usable)
        if t in CATEGORY_LIKE:
            _variants(ctx, col, s, usable, t)
        if t == "date":
            _dates(ctx, col, s, usable)
        if t == "money":
            _money(ctx, col, s, usable)


def _whitespace(ctx, col, s, usable):
    edge = s != s.str.strip()
    inner = s.str.contains("  ", regex=False)
    if inner.any():
        # an internal double space is only an error if the single-spaced form also occurs
        single = set(s[usable & ~inner].str.strip())
        inner &= s.map(lambda x: " ".join(x.split()) in single)
    bad = usable & (edge | inner)
    for rid in bad[bad].index:
        ctx.add(rid, col, "inconsistent", "consistency:whitespace", f"{col} has stray spaces", s[rid],
                kind="whitespace", suggestion=" ".join(s[rid].split()))


def _case(ctx, col, s, usable):
    vals = s[usable].str.strip()
    upper = vals.str.isupper() & (vals.str.len() > 3)
    if 0 < upper.mean() < 0.1:
        for rid in upper[upper].index:
            ctx.add(rid, col, "inconsistent", "consistency:case", f"{col} is in ALL CAPS unlike the rest", s[rid],
                    kind="case", suggestion=s[rid].strip().title())


def _short_close(a: str, b: str) -> bool:
    n = max(len(a), len(b))
    if n <= 6:
        return OSA.distance(a, b) <= 1
    if n <= 12:
        return OSA.distance(a, b) <= 2 and fuzz.ratio(a, b) >= 80
    return fuzz.ratio(a, b) >= 85


def _variants(ctx, col, s, usable, t):
    vals = s[usable]
    raw_counts = vals.value_counts()
    # 1) same key, different raw form (case / punctuation / spacing)
    key_of = {raw: v.norm_key(raw) for raw in raw_counts.index}
    by_key: dict[str, Counter] = {}
    for raw, n in raw_counts.items():
        by_key.setdefault(key_of[raw], Counter())[raw] = n
    canon_raw = {k: c.most_common(1)[0][0] for k, c in by_key.items()}
    key_count = {k: sum(c.values()) for k, c in by_key.items()}

    canonical: dict[str, str] = {}
    reason: dict[str, tuple[str, str, dict]] = {}
    for raw in raw_counts.index:
        canonical[raw] = canon_raw[key_of[raw]]
        if canonical[raw] != raw and raw.strip() != canonical[raw]:
            reason[raw] = ("variant", f"{col} '{raw}' is written differently from '{canonical[raw]}'", {})

    # 2) known aliases (Bombay -> Mumbai)
    if t in ("city", "district", "state", "category"):
        present = {k: canon_raw[k] for k in by_key}
        for k in by_key:
            target = CITY_ALIASES.get(k)
            # only when both forms are in use; a column consistently using "Bangalore" is not an error
            if target and v.norm_key(target) in present:
                tk = v.norm_key(target)
                display = present.get(tk, target)
                for raw in by_key[k]:
                    canonical[raw] = display
                    reason[raw] = ("alias", f"{col} '{raw}' is an old/alternate name for '{display}'",
                                   {"alias_of": display})

    # 3) rare spelling near a frequent value
    frequent = [k for k, n in key_count.items() if n >= 5]
    alias_keys = [a for a in CITY_ALIASES if v.norm_key(CITY_ALIASES[a]) in key_count] if t != "category" else []
    for k, n in key_count.items():
        if any(reason.get(raw, ("",))[0] == "alias" for raw in by_key[k]):
            continue
        best, best_score = None, 0.0
        for f in frequent:
            if f == k or key_count[f] < 20 * n:
                continue
            if _short_close(k, f):
                score = fuzz.ratio(k, f)
                if score > best_score:
                    best, best_score = f, score
        if best is None:
            for a in alias_keys:  # misspelling of a known alias: Banglore ~ Bangalore -> Bengaluru
                if a != k and _short_close(k, a):
                    best, best_score = a, fuzz.ratio(k, a)
                    break
        if best is not None:
            target_key = v.norm_key(CITY_ALIASES.get(best, "")) or best
            target = canon_raw.get(target_key) or CITY_ALIASES.get(best) or canon_raw[best]
            similar_to = canon_raw.get(best) or best.title()
            for raw in by_key[k]:
                canonical[raw] = target
                reason[raw] = ("spelling", f"{col} '{raw}' looks like a misspelling of '{target}'",
                               {"similar_to": similar_to, "similarity": round(best_score, 1)})

    ctx.canonical[col] = canonical
    for rid, raw in vals.items():
        if raw in reason:
            kind, msg, meta = reason[raw]
            ctx.add(rid, col, "inconsistent", f"consistency:{kind}", msg, raw, kind=kind,
                    suggestion=canonical[raw], **meta)


def _dates(ctx, col, s, usable):
    fams = {rid: v.date_families(x) for rid, x in s[usable].items()}
    unambiguous = Counter(next(iter(f)) for f in fams.values() if len(f) == 1)
    if not unambiguous:
        return
    dominant, n_dom = unambiguous.most_common(1)[0]
    if n_dom / max(sum(unambiguous.values()), 1) < 0.6:
        return
    for rid, f in fams.items():
        if f and dominant not in f:
            ctx.add(rid, col, "inconsistent", "consistency:date_format",
                    f"{col} is written as {'/'.join(sorted(f))} while the column uses {dominant}", s[rid],
                    kind="date_format", dominant=dominant, found=sorted(f))


def _money(ctx, col, s, usable):
    styles = s[usable].map(v.money_style)
    counts = styles.value_counts()
    if counts.empty:
        return
    dominant = counts.index[0]
    if counts.iloc[0] / counts.sum() < 0.6:
        return
    odd = styles[styles != dominant]
    for rid, style in odd.items():
        amount = v.parse_money(s[rid])
        if amount is None:
            continue
        ctx.add(rid, col, "inconsistent", "consistency:money_format",
                f"{col} uses {style} notation; the column uses {dominant}", s[rid], kind="money_format",
                suggestion=f"{amount:.0f}" if amount == int(amount) else f"{amount}", dominant=dominant)
