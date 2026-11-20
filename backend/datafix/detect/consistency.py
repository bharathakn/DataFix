"""Inconsistent representations: whitespace, case, variants, aliases, spelling, mixed date/money formats.

Also builds ctx.canonical[col] (raw -> canonical value) so later detectors (FD) see one value per entity.
"""
import re
from collections import Counter

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import OSA

from .. import validators as v
from ..knowledge import CITY_ALIASES, GST_STATE_CODES, STATE_CODES, TERM_ALIASES, VALUE_FAMILIES
from . import CATEGORY_LIKE, ScanContext

_NO_WHITESPACE_CHECK = {"text"}


def detect_consistency(ctx: ScanContext) -> None:
    for col, info in ctx.columns.items():
        t = info.semantic_type
        s = ctx.df[col]
        usable = ctx.usable(col)
        if t in _CANONICAL:  # before whitespace: one issue per cell type, and this suggestion covers spaces too
            _canonical(ctx, col, s, t)
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


_WORD = r"[A-Z][a-z]*\.?(?:['-][A-Z]?[a-z]+)*"  # Rahul, D'Souza, Jean-Luc, Dr.
_NAME_TITLE = re.compile(rf"^{_WORD}(?: {_WORD})*$")


def _canon_phone(x: str) -> str | None:
    n = v.normalize_phone(x)
    return n if v.PHONE_RE.match(n) else None


def _canon_email(x: str) -> str | None:
    n = x.strip().lower()
    return n if v.is_email(n) else None


def _canon_pan(x: str) -> str | None:
    n = x.strip().upper()
    return n if v.is_pan(n) else None


def _canon_pin(x: str) -> str | None:
    if v.is_pin_format(x) and x == x.strip():
        return x
    m = re.fullmatch(r"\s*([1-9]\d{5})\.0+\s*", x)  # Excel float artifact: 560013.0
    return m.group(1) if m else None


def _canon_name(x: str) -> str | None:
    n = " ".join(x.split())
    if not n or not re.fullmatch(r"[A-Za-z'. -]+", n):
        return None
    if n == x and _NAME_TITLE.match(n):
        return n  # already canonical
    # only all-lower, ALL-UPPER or sWAPPED case; mixed forms like McDonald are left alone
    if n.islower() or n.isupper() or n.swapcase() == n.swapcase().title():
        t = n.title()
        return t if _NAME_TITLE.match(t) else None
    return None


# column type -> (canonical form or None, share of present values that must already be canonical, label)
_CANONICAL = {
    "phone": (_canon_phone, 0.6, "a plain 10-digit mobile number"),
    "email": (_canon_email, 0.6, "lower case without spaces"),
    "pan": (_canon_pan, 0.6, "upper case"),
    "pin": (_canon_pin, 0.6, "a 6-digit PIN"),
    "name": (_canon_name, 0.9, "Title Case with single spaces"),
}


def _canonical(ctx, col, s, t):
    """Values that are valid but not written the way most of the column is (phone '+91 98450 12345',
    'A.B@GMAIL.COM ', 'abcpd1234e', '560013.0', 'rAHUL sHARMA'). Flagged only when the canonical form
    already dominates the column."""
    fn, need, label = _CANONICAL[t]
    present = s[~ctx.unusable[col]]
    if present.empty:
        return
    canon = {x: fn(x) for x in present.unique()}
    already = present.map(lambda x: canon[x] == x).mean()
    if already < need:
        return
    for rid, x in present.items():
        c = canon[x]
        if c is not None and c != x:
            ctx.add(rid, col, "inconsistent", "consistency:canonical", f"{col} is not written as {label}", x,
                    kind="canonical", suggestion=c)


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
        # suggest the form the column already uses for the same value (MUMBAI -> Mumbai), else Title Case
        written = {}
        for x, n in vals[~upper].value_counts().items():
            written.setdefault(v.norm_key(x), x)
        for rid in upper[upper].index:
            raw = s[rid].strip()
            ctx.add(rid, col, "inconsistent", "consistency:case", f"{col} is in ALL CAPS unlike the rest", s[rid],
                    kind="case", suggestion=written.get(v.norm_key(raw), raw.title()))


def _family_map(key_count: dict[str, int], by_key: dict[str, Counter]) -> dict[str, str] | None:
    """key -> display form when the column's values (>= 95%) all come from one VALUE_FAMILIES family
    and at least two of its styles are in use. The display form per meaning comes from the most used style."""
    total = sum(key_count.values())
    if not total:
        return None
    for styles in VALUE_FAMILIES.values():
        members = {k for st in styles for k in st}
        covered = sum(n for k, n in key_count.items() if k in members)
        used = [st for st in styles if any(k in key_count for k in st)]
        if covered / total < 0.95 or len(used) < 2:
            continue
        best = max(used, key=lambda st: sum(key_count.get(k, 0) for k in st))
        out = {}
        for i, target in enumerate(best):
            if target not in key_count:
                continue  # meaning never written in the main style: leave other styles alone
            display = by_key[target].most_common(1)[0][0].strip()
            for st in styles:
                if st[i] in key_count:
                    out[st[i]] = display
        return out
    return None


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

    # 1b) one value family written in several styles (yes/Y/1/Active -> true; m/F -> Male/Female)
    fam = _family_map(key_count, by_key)
    if fam:
        for k, display in fam.items():
            for raw in by_key[k]:
                if raw.strip() != display:
                    canonical[raw] = display
                    reason[raw] = ("synonym", f"{col} '{raw}' means '{display}', the form most of the column uses", {})

    # 2) known aliases (Bombay -> Mumbai)
    if t in ("city", "district", "state", "category"):
        present = {k: canon_raw[k] for k in by_key}
        for k in by_key:
            target = CITY_ALIASES.get(k) or (TERM_ALIASES.get(k) if t == "category" else None) or (
                STATE_CODES.get(k) if t == "state" else None)
            # only when both forms are in use; a column consistently using "Bangalore" is not an error
            if target and v.norm_key(target) in present:
                tk = v.norm_key(target)
                display = present.get(tk, target)
                for raw in by_key[k]:
                    canonical[raw] = display
                    reason[raw] = ("alias", f"{col} '{raw}' is an old/alternate name for '{display}'",
                                   {"alias_of": display})

    # 3) rare spelling near a frequent value. Targets are counted after alias/synonym mapping (KA -> Karnataka),
    # so the result is the same whether or not those mappings were already applied (idempotence).
    mapped = Counter()
    for raw, n in raw_counts.items():
        mapped[v.norm_key(canonical[raw])] += n
    target_count = {k: max(key_count[k], mapped.get(k, 0)) for k in key_count}
    frequent = [k for k, n in target_count.items() if n >= 5]
    # state columns have an official list: a close misspelling of an official name needs no frequency ratio
    official = {v.norm_key(x) for x in (*STATE_CODES.values(), *GST_STATE_CODES.values())} if t == "state" else set()
    alias_keys = [a for a in CITY_ALIASES if v.norm_key(CITY_ALIASES[a]) in key_count] if t != "category" else []
    for k, n in key_count.items():
        if any(reason.get(raw, ("",))[0] == "alias" for raw in by_key[k]):
            continue
        best, best_score = None, 0.0
        for f in frequent:
            if f == k or (target_count[f] < 20 * n and not (f in official and k not in official)):
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

    if t == "category":
        _abbreviations(raw_counts, key_count, canon_raw, by_key, canonical, reason, col)
    ctx.canonical[col] = canonical
    if t == "category":
        _outside_domain(ctx, col, vals, key_count, canon_raw, by_key, reason)
    for rid, raw in vals.items():
        if raw in reason:
            kind, msg, meta = reason[raw]
            ctx.add(rid, col, "inconsistent", f"consistency:{kind}", msg, raw, kind=kind,
                    suggestion=canonical[raw], **meta)


RARE = 2  # a value written at most this often is "rare" in a category column
FREQUENT = 5


def _abbreviations(raw_counts, key_count, canon_raw, by_key, canonical, reason, col):
    """A rare one- or two-letter value that starts exactly one frequent value ('A' -> 'Active').
    Only a suggestion: the code could mean something else, so the repair stays in review."""
    frequent = [k for k, n in key_count.items() if n >= FREQUENT and len(k) > 2]
    for k, n in key_count.items():
        if n > RARE or not (1 <= len(k) <= 2) or not k.isalpha() or any(r in reason for r in by_key[k]):
            continue
        starts = [f for f in frequent if f.startswith(k)]
        if len(starts) != 1:
            continue
        target = canon_raw[starts[0]]
        for raw in by_key[k]:
            canonical[raw] = target
            reason[raw] = ("abbreviation", f"{col} '{raw}' may be short for '{target}', the only common value "
                           f"starting with '{raw.strip()}'", {"abbreviation_of": target})


def _outside_domain(ctx, col, vals, key_count, canon_raw, by_key, reason):
    """In a column with a small, settled set of values (Active / Inactive), a value written once that matches
    none of them is outside the column's domain. Flagged with no suggestion: mapping it needs a confirmed rule."""
    total = sum(key_count.values())
    frequent = [k for k, n in key_count.items() if n >= FREQUENT]
    if total < 30 or not 2 <= len(frequent) <= 10 or sum(key_count[k] for k in frequent) < 0.9 * total:
        return
    allowed = ", ".join(canon_raw[k] for k in sorted(frequent, key=lambda k: -key_count[k]))
    for k, n in key_count.items():
        if n != 1 or k in frequent or any(r in reason for r in by_key[k]):
            continue
        for rid, raw in vals[vals.map(v.norm_key) == k].items():
            ctx.add(rid, col, "invalid_format", "category:outside_domain",
                    f"{col} '{raw.strip()}' is not one of the column's established values ({allowed})", raw,
                    kind="outside_domain", allowed=allowed)


def _dates(ctx, col, s, usable):
    fams = {rid: v.date_families(x) for rid, x in s[usable].items()}
    unambiguous = Counter(next(iter(f)) for f in fams.values() if len(f) == 1)
    if not unambiguous:
        return
    dominant, n_dom = unambiguous.most_common(1)[0]
    if n_dom / max(sum(unambiguous.values()), 1) < 0.6:
        return
    # within the dominant family, the written shape can still differ (2025/07/03 in a YYYY-MM-DD column)
    shape = Counter(_shape(s[rid]) for rid, f in fams.items() if f == frozenset({dominant}))
    main_shape, n_shape = shape.most_common(1)[0] if shape else ("", 0)
    shape_ok = n_shape / max(sum(shape.values()), 1) >= 0.8
    for rid, f in fams.items():
        if f and dominant not in f:
            ctx.add(rid, col, "inconsistent", "consistency:date_format",
                    f"{col} is written as {'/'.join(sorted(f))} while the column uses {dominant}", s[rid],
                    kind="date_format", dominant=dominant, found=sorted(f))
        elif shape_ok and f == frozenset({dominant}) and _shape(s[rid]) != main_shape:
            ctx.add(rid, col, "inconsistent", "consistency:date_format",
                    f"{col} '{s[rid].strip()}' uses different separators from the rest of the column", s[rid],
                    kind="date_format", dominant=dominant, found=[dominant], same_family=True)


def _shape(x: str) -> str:
    """Digits -> 9, letters -> a: '2025-07-03' -> '9999-99-99'."""
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", x.strip()))


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
