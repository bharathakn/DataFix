"""Issues -> RepairProposals with ranked candidates, tiers and refusals."""
import time
from collections import Counter

import pandas as pd

from .confidence import CAPS, DEFAULT_CAP, rank, signal, tier_for
from .detect import CATEGORY_LIKE
from .models import Issue, RepairProposal
from .reference import pin_reference
from .repair import ERROR_TYPES, Linked, RepairContext, find_joins
from .repair.age import repair_age
from .repair.category import repair_category
from .repair.contact import repair_email, repair_phone
from .repair.outcome import Outcome, refuse
from .repair.pin import repair_pin
from .repair.rows import fix_total, merge_duplicate
from .repair.text import fix_date, fix_encoding, fix_money, fix_text
from .scan import ScanResult


def _dispatch(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome | None:
    types = {i.type for i in issues}
    kinds = {i.meta.get("kind") for i in issues}
    t = ctx.col_type(col)
    if not types & ERROR_TYPES:
        if "anomaly" in types:
            return Outcome("none", "flag_only", refusal="unusual but possible value: flagged for a human, never "
                                                        "changed automatically", meta={"flag_only": True})
        return None
    canon = next((i.meta["suggestion"] for i in issues if i.meta.get("kind") == "canonical"), None)
    if canon is not None and not types & {"missing", "disguised_missing", "fd_violation", "crossfield"}:
        return Outcome("normalize", "canonical_format", {canon: [signal(
            "deterministic_transform", 1.0, f"same value in the form most of {col} uses ({issues[0].message.split(' as ')[-1]})")]})
    if "encoding" in kinds:
        return fix_encoding(ctx, row, col, issues)
    if t == "pin":
        return repair_pin(ctx, row, col, issues)
    if t == "phone":
        return repair_phone(ctx, row, col, issues)
    if t == "email":
        return repair_email(ctx, row, col, issues)
    if t == "age":
        return repair_age(ctx, row, col, issues)
    if t in CATEGORY_LIKE:
        return repair_category(ctx, row, col, issues)
    if "date_format" in kinds:
        return fix_date(ctx, row, col, issues)
    if "money_format" in kinds:
        return fix_money(ctx, row, col, issues)
    if "crossfield" in types:
        return fix_total(ctx, row, col, issues)
    if kinds & {"whitespace", "case"}:
        return fix_text(ctx, row, col, issues)
    if types & {"missing", "disguised_missing"}:
        return refuse("recover", "none", f"no rule, reference or linked record can supply {col}")
    return refuse("none", "none", f"no safe repair method for this {t} value")


def _proposal(pid: str, table: str, row: int, col: str, original: str, issues: list[Issue], out: Outcome,
              thresholds: dict | None) -> RepairProposal:
    meta = dict(out.meta)
    if out.refusal:
        tier = "flag" if meta.pop("flag_only", False) else "refused"
        return RepairProposal(pid, table, [i.issue_id for i in issues], row, col, original, [], tier,
                              out.repair_class, out.algorithm, out.refusal, meta=meta)
    cands = rank(out.candidates, CAPS.get(out.cap_key, DEFAULT_CAP))
    if not cands:
        return RepairProposal(pid, table, [i.issue_id for i in issues], row, col, original, [], "refused",
                              out.repair_class, out.algorithm, "no candidate had supporting evidence", meta=meta)
    tier = tier_for(cands[0].confidence, thresholds)
    return RepairProposal(pid, table, [i.issue_id for i in issues], row, col, original, cands, tier,
                          out.repair_class, out.algorithm, meta=meta)


def plan_repairs(tables: dict[str, pd.DataFrame], scans: dict[str, ScanResult],
                 thresholds: dict | None = None) -> list[RepairProposal]:
    ref = pin_reference()
    proposals: list[RepairProposal] = []
    for name, df in tables.items():
        linked = [Linked(o, tables[o], scans[o], find_joins(scans[name], scans[o])) for o in tables if o != name]
        ctx = RepairContext(name, df, scans[name], ref, [lk for lk in linked if lk.joins])
        for (row, col), issues in sorted(ctx.cells.items()):
            out = _dispatch(ctx, row, col, issues)
            if out is None:
                continue
            proposals.append(_proposal("", name, row, col, df.at[row, col], issues, out, thresholds))
        for issue in scans[name].issues:
            if issue.type in ("duplicate", "near_duplicate"):
                out = merge_duplicate(ctx, issue)
                proposals.append(_proposal("", name, issue.row_id, "__row__", "", [issue], out, thresholds))
    for n, p in enumerate(proposals, 1):
        p.proposal_id = f"P{n:05d}"
    return proposals


def summarize(proposals: list[RepairProposal]) -> dict:
    return {
        "tiers": dict(Counter(p.tier for p in proposals)),
        "by_class": {f"{c} / {t}": n for (c, t), n in sorted(Counter((p.repair_class, p.tier) for p in proposals).items())},
    }


def preview_apply(tables: dict[str, pd.DataFrame], proposals: list[RepairProposal],
                  tiers: tuple[str, ...] = ("auto",)) -> dict[str, pd.DataFrame]:
    """Apply top candidates of the given tiers to copies (no audit trail; Phase 2B adds the real session)."""
    out = {n: df.copy() for n, df in tables.items()}
    drop: dict[str, set[int]] = {n: set() for n in tables}
    for p in proposals:
        if p.tier not in tiers or not p.candidates:
            continue
        df = out[p.table]
        if p.column == "__row__":
            drop[p.table].add(p.row_id)
            survivor = p.meta["survivor"]
            for c, val in p.meta["fills"].items():
                if df.at[survivor, c].strip() == "":
                    df.at[survivor, c] = val
            for r in p.meta["fk_remaps"]:
                out[r["table"]].at[r["row_id"], r["column"]] = r["new"]
        else:
            df.at[p.row_id, p.column] = p.candidates[0].value
    return {n: df.drop(index=sorted(drop[n])) for n, df in out.items()}


def plan_tables(paths: dict[str, str]) -> tuple[dict, dict, list[RepairProposal], dict]:
    """Convenience for CLI/tests: load, scan and plan named files."""
    from .ingest import load_path
    from .scan import scan_table
    t0 = time.perf_counter()
    tables = {n: load_path(p).df for n, p in paths.items()}
    scans = {n: scan_table(df, n) for n, df in tables.items()}
    t1 = time.perf_counter()
    proposals = plan_repairs(tables, scans)
    timings = {"scan_ms": int((t1 - t0) * 1000), "plan_ms": int((time.perf_counter() - t1) * 1000)}
    return tables, scans, proposals, timings
