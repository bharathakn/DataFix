"""Cross-field rules: total = quantity x price, GSTIN vs PAN and state, age vs date of birth."""
from datetime import date, timedelta

import numpy as np

from .. import validators as v
from ..knowledge import GST_STATE_CODES
from ..models import LearnedRule
from . import ScanContext
from ..coltypes import header_tokens

QTY = {"qty", "quantity", "units", "count"}
PRICE = {"price", "rate", "unit_price", "mrp"}
TOTAL = {"total", "amount", "line_total", "subtotal"}


def _find(ctx: ScanContext, names: set[str]) -> str | None:
    for col in ctx.columns:
        toks = header_tokens(col)
        if col.lower() in names or (toks and toks[-1] in names):
            return col
    return None


def detect_crossfield(ctx: ScanContext) -> None:
    _product_rule(ctx)
    _gstin_rules(ctx)
    _age_dob_rule(ctx)


AGE_RULE_MIN_SUPPORT = 50
AGE_RULE_MIN_AGREEMENT = 0.9


def parse_dob(x: str) -> date | None:
    """A date of birth only when every reading of it gives the same day (03/04/1990 is ambiguous)."""
    fams = v.date_families(x)
    days = {d.date() for f in fams if (d := v.parse_date(x, prefer=f)) is not None}
    return next(iter(days)) if len(days) == 1 else None


def age_on(dob: date, ref: date) -> int:
    return ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))


def learn_age_rule(df, age_col: str, dob_col: str, usable_age, usable_dob, today: date | None = None) -> dict | None:
    """Learn 'age = whole years from dob to REF' from rows where both look valid. REF is the day in the last
    two years that makes the most rows agree (data is often exported days or months before it is cleaned).
    Returns {ref, agreement, support} only if the rule holds for >= 90% of at least 50 rows."""
    today = today or date.today()
    rows = [(r, int(df.at[r, age_col].strip()), d) for r in df.index[usable_age & usable_dob]
            if v.is_age(df.at[r, age_col]) and (d := parse_dob(df.at[r, dob_col])) is not None]
    if len(rows) < AGE_RULE_MIN_SUPPORT:
        return None
    ages = np.array([a for _, a, _ in rows])
    y = np.array([d.year for *_, d in rows])
    md = np.array([d.month * 100 + d.day for *_, d in rows])
    best = (-1.0, today)
    for back in range(0, 731):
        ref = today - timedelta(days=back)
        agree = float(np.mean(ref.year - y - ((ref.month * 100 + ref.day) < md) == ages))
        if agree > best[0]:
            best = (agree, ref)
    if best[0] < AGE_RULE_MIN_AGREEMENT:
        return None
    return {"ref": best[1], "agreement": round(best[0], 4), "support": len(rows)}


def find_age_dob(columns) -> tuple[str, str] | None:
    age = next((c for c, i in columns.items() if i.semantic_type == "age"), None)
    dobs = [c for c, i in columns.items() if i.semantic_type == "date"
            and (c.lower() in ("dob", "birth_date", "date_of_birth", "birthdate") or "birth" in c.lower())]
    return (age, dobs[0]) if age and dobs else None


def _age_dob_rule(ctx: ScanContext) -> None:
    cols = find_age_dob(ctx.columns)
    if not cols:
        return
    a, d = cols
    rule = learn_age_rule(ctx.df, a, d, ctx.usable(a), ~ctx.unusable[d])
    if not rule:
        return
    ref, bad = rule["ref"], 0
    m = ctx.usable(a) & ~ctx.unusable[d]
    for rid in m[m].index:
        x = ctx.df.at[rid, a].strip()
        dob = parse_dob(ctx.df.at[rid, d])
        if dob is None or not v.is_age(x):
            continue
        expected = age_on(dob, ref)
        if int(x) != expected:
            bad += 1
            ctx.add(rid, a, "crossfield", f"crossfield:{a}~{d}",
                    f"{a} {x} does not match {d} {ctx.df.at[rid, d]} (age {expected} on {ref.isoformat()})",
                    x, expected=str(expected), kind="age_dob")
    ctx.rules.append(LearnedRule(f"X{len(ctx.rules) + 1:02d}", "crossfield", d, a,
                                 f"{a} = whole years from {d} to {ref.isoformat()}", rule["support"],
                                 rule["agreement"], bad))


def _product_rule(ctx: ScanContext) -> None:
    q, p, t = _find(ctx, QTY), _find(ctx, PRICE), _find(ctx, TOTAL)
    if not (q and p and t) or len({q, p, t}) < 3:
        return
    m = ctx.usable(q) & ctx.usable(p) & ctx.usable(t)
    checked = bad = 0
    for rid in m[m].index:
        qv, pv, tv = (v.parse_money(ctx.df.at[rid, c]) for c in (q, p, t))
        if None in (qv, pv, tv):
            continue
        checked += 1
        expected = qv * pv
        if abs(tv - expected) > max(1e-4 * abs(expected), 0.01):
            bad += 1
            ctx.add(rid, t, "crossfield", f"crossfield:{t}={q}x{p}",
                    f"{t} {ctx.df.at[rid, t]} ≠ {q} {ctx.df.at[rid, q]} × {p} {ctx.df.at[rid, p]} = {expected:g}",
                    ctx.df.at[rid, t], expected=f"{expected:g}")
    if checked:
        ctx.rules.append(LearnedRule(f"X{len(ctx.rules) + 1:02d}", "crossfield", f"{q},{p}", t,
                                     f"{t} = {q} × {p}", checked, round(1 - bad / checked, 4), bad))


def _gstin_rules(ctx: ScanContext) -> None:
    g = next((c for c, i in ctx.columns.items() if i.semantic_type == "gstin"), None)
    if not g:
        return
    pan = next((c for c, i in ctx.columns.items() if i.semantic_type == "pan"), None)
    state = next((c for c, i in ctx.columns.items() if i.semantic_type == "state"), None)
    m = ctx.usable(g)
    for rid in m[m].index:
        gst = ctx.df.at[rid, g].strip()
        if pan and ctx.usable(pan)[rid] and gst[2:12] != ctx.df.at[rid, pan].strip():
            ctx.add(rid, pan, "crossfield", f"crossfield:{g}~{pan}", f"PAN does not match the PAN inside GSTIN {gst}",
                    ctx.df.at[rid, pan], expected=gst[2:12])
        if state and ctx.usable(state)[rid]:
            expected = GST_STATE_CODES.get(gst[:2])
            if expected and v.norm_key(expected) != v.norm_key(ctx.df.at[rid, state]):
                ctx.add(rid, state, "crossfield", f"crossfield:{g}~{state}",
                        f"GSTIN state code {gst[:2]} means {expected}, but state is '{ctx.df.at[rid, state]}'",
                        ctx.df.at[rid, state], expected=expected)
