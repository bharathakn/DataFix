"""Row-level repairs: duplicate merges (with foreign-key remap) and cross-field totals."""
from ..confidence import signal
from ..models import Issue
from . import RepairContext, _build_index
from .outcome import Outcome


def merge_duplicate(ctx: RepairContext, issue: Issue) -> Outcome:
    dup, root = issue.row_id, issue.meta["duplicate_of"]
    near = issue.type == "near_duplicate"
    fills = {}
    for c in ctx.df.columns:
        if ctx.col_type(c) == "text":  # free-text notes belong to their own record; never copied across
            continue
        if ctx.df.at[root, c].strip() == "" and ctx.df.at[dup, c].strip() and not ctx.is_error(dup, c):
            fills[c] = ctx.df.at[dup, c]
    remaps = []
    for lk in ctx.linked:
        for main_col, link_col in lk.joins:
            if ctx.col_type(main_col) != "id":
                continue
            old, new = ctx.df.at[dup, main_col], ctx.df.at[root, main_col]
            if old == new:
                continue
            if link_col not in lk.index:
                lk.index[link_col] = _build_index(lk.df[link_col], ctx.col_type(main_col))
            for r in lk.index[link_col].get(old.strip(), []):
                remaps.append({"table": lk.name, "row_id": int(r), "column": link_col, "old": old, "new": new})
    if near:
        sigs = [signal("record_match", issue.meta.get("similarity", 90) / 100,
                       f"row {dup} matches row {root} on every date/ID/phone field and is "
                       f"{issue.meta.get('similarity', 90):.0f}% similar overall")]
        cap = "near_duplicate"
    else:
        ids = [c for c in ctx.df.columns if ctx.col_type(c) == "id"
               and ctx.df.at[dup, c].strip() != ctx.df.at[root, c].strip()]
        if ids:
            # identical content under a different record ID: almost surely a re-entry, but removing a record
            # that has its own ID is a person's decision (the ID may be referenced elsewhere)
            sigs = [signal("deterministic_transform", 1.0,
                           f"row {dup} is identical to row {root} apart from its {ids[0]} "
                           f"('{ctx.df.at[dup, ids[0]].strip()}' vs '{ctx.df.at[root, ids[0]].strip()}')")]
            cap = "distinct_id_duplicate"
        else:
            sigs = [signal("deterministic_transform", 1.0, f"row {dup} is identical to row {root}")]
            cap = None
    if remaps:
        sigs.append(signal("records_agree", 0.0,
                           f"{len(remaps)} linked record(s) will be re-pointed to the surviving row"))
    return Outcome("dedupe_merge", "near_duplicate_merge" if near else "exact_duplicate_merge",
                   {f"merge_into:{root}": sigs}, cap_key=cap,
                   meta={"survivor": int(root), "fills": fills, "fk_remaps": remaps})


def fix_total(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    issue = next(i for i in issues if i.type == "crossfield")
    expected = issue.meta["expected"]
    rule = next((r for r in ctx.scan.rules if r.rhs == col and r.kind == "crossfield"), None)
    conf = rule.confidence if rule else 0.9
    return Outcome("correct", "crossfield_total", {expected: [signal(
        "crossfield_rule", conf,
        f"{issue.message}; the rule holds in {conf:.1%} of rows. Quantity or price could also be the wrong field")]})

