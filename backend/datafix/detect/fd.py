"""Functional-dependency discovery: rules learned from the data itself (docs/05_ENGINE_SPEC.md §4.1)."""
import pandas as pd

from .. import validators as v
from ..models import LearnedRule
from . import CATEGORY_LIKE, ScanContext

FD_TYPES = CATEGORY_LIKE | {"pin", "id"}
MIN_GROUP = 3
MIN_GROUPS = 5
MIN_CONFIDENCE = 0.95
MAX_BASELINE_SHARE = 0.8  # Y must not be near-constant, or every X "determines" it
MIN_MAJORITY_SHARE = 0.8  # only flag minority rows in clearly-decided groups


def _keys(ctx: ScanContext, col: str) -> pd.Series:
    canon = ctx.canonical.get(col, {})
    s = ctx.df[col].map(lambda x: v.norm_key(canon.get(x, x)))
    return s.where(ctx.usable(col), "")


def detect_fd(ctx: ScanContext) -> None:
    cand = [c for c, i in ctx.columns.items() if i.semantic_type in FD_TYPES and c not in ctx.sparse][:20]
    keys = {c: _keys(ctx, c) for c in cand}
    violations: list[tuple[int, str, str, str, dict]] = []
    majorities: dict[str, tuple[str, str, float, dict]] = {}  # rule_id -> (lhs, rhs, conf, key->majority key)

    for x in cand:
        xs = keys[x]
        vx = xs != ""
        if vx.sum() < 50 or xs[vx].nunique() > 0.9 * vx.sum():
            continue
        for y in cand:
            if y == x or ctx.columns[y].semantic_type == "id":
                continue
            ys = keys[y]
            m = vx & (ys != "")
            if m.sum() < 50 or ys[m].value_counts(normalize=True).iloc[0] > MAX_BASELINE_SHARE:
                continue
            pair = pd.DataFrame({"x": xs[m], "y": ys[m]})
            counts = pair.groupby(["x", "y"]).size()
            size = counts.groupby(level=0).sum()
            top = counts.groupby(level=0).max()
            supported = size[size >= MIN_GROUP].index
            if len(supported) < MIN_GROUPS:
                continue
            conf = top[supported].sum() / size[supported].sum()
            if conf < MIN_CONFIDENCE or size[supported].sum() < 0.5 * m.sum():
                continue
            majority = counts.groupby(level=0).idxmax().map(lambda t: t[1])
            share = top / size
            rule_id = f"R{len(ctx.rules) + 1:02d}"
            rule = LearnedRule(rule_id, "fd", x, y, f"{x} determines {y}", int(size[supported].sum()),
                               round(float(conf), 4))
            ctx.rules.append(rule)
            majorities[rule_id] = (x, y, float(conf), majority.to_dict())

            decided = set(share[(share >= MIN_MAJORITY_SHARE) & (size >= MIN_GROUP)].index)
            sub = pair[pair["x"].isin(decided)]
            bad = sub[sub["y"] != sub["x"].map(majority)]
            maj_raw = _majority_raw(ctx, x, y, m)
            for rid, row in bad.iterrows():
                violations.append((rid, x, y, rule_id, {
                    "rule": rule_id, "lhs_value": ctx.df.at[rid, x], "expected": maj_raw.get(row["x"], row["x"]),
                    "group_size": int(size[row["x"]]), "majority_share": round(float(share[row["x"]]), 3)}))

    # A violation of X->Y is unreliable if X itself is suspect in that row.
    suspect = {(rid, y) for rid, _, y, _, _ in violations} | ctx.flagged_cells(
        {"inconsistent", "invalid_format", "missing", "disguised_missing"})
    by_rule = {r.rule_id: r for r in ctx.rules}
    for rid, x, y, rule_id, meta in violations:
        if (rid, x) in suspect or _explained(rid, x, y, rule_id, keys, majorities):
            continue
        by_rule[rule_id].violations += 1
        ctx.add(rid, y, "fd_violation", f"fd:{x}->{y}",
                f"{y} '{ctx.df.at[rid, y]}' disagrees with {x} {meta['lhs_value']} "
                f"(learned rule: {meta['majority_share']:.0%} of {meta['group_size']} rows say '{meta['expected']}')",
                ctx.df.at[rid, y], **meta)


def _explained(rid, x, y, rule_id, keys, majorities) -> bool:
    """A stronger rule Z->Y that agrees with the row's Y explains the disagreement
    (e.g. PIN 400001 spans two districts, but locality pins the district exactly)."""
    conf = majorities[rule_id][2]
    for other, (z, rhs, c, maj) in majorities.items():
        if other != rule_id and rhs == y and z != x and c >= conf:
            zk = keys[z][rid]
            if zk and maj.get(zk) == keys[y][rid]:
                return True
    return False


def _majority_raw(ctx: ScanContext, x: str, y: str, m: pd.Series) -> dict[str, str]:
    """Map each X key to the most common *raw* Y spelling, for readable messages."""
    canon = ctx.canonical.get(y, {})
    raw_y = ctx.df[y][m].map(lambda val: canon.get(val, val).strip())
    df = pd.DataFrame({"x": _keys(ctx, x)[m], "y": raw_y})
    return df.groupby("x")["y"].agg(lambda s: s.value_counts().index[0]).to_dict()
