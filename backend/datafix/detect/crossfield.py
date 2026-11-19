"""Cross-field rules: total = quantity x price, GSTIN vs PAN and state."""
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
