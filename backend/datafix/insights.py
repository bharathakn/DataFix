"""Read models for the UI: warnings, heatmap, paged rows with cell states, row detail, proposal groups."""
import math
from collections import Counter, defaultdict

from . import validators as v
from .diagnose import _label

ROW = "__row__"
ERROR_TYPES = {"missing", "disguised_missing", "invalid_format", "inconsistent", "fd_violation", "crossfield"}
HIGH = {"duplicate", "near_duplicate", "fd_violation", "disguised_missing", "crossfield"}
ACTIONS = {
    "missing": "Recover from learned rules or linked records where evidence exists; the rest need the source.",
    "disguised_missing": "Treat as blank, then recover from linked records where possible.",
    "invalid_format": "Repair from evidence (reference data, linked records) or send to review.",
    "inconsistent": "Standardise to the column's dominant form.",
    "fd_violation": "Correct to the value the learned rule expects, after review of the evidence.",
    "crossfield": "Review which field is wrong; DataFix suggests the computed value.",
    "duplicate": "Merge into the earlier record; linked records are re-pointed.",
    "near_duplicate": "Review the pair and merge if they are the same record.",
    "anomaly": "Check manually: unusual is not necessarily wrong. DataFix will not change it.",
}


def warnings(scan, n_rows: int) -> list[dict]:
    groups: dict[tuple, list] = defaultdict(list)
    for i in scan.issues:
        if i.row_id is None:
            continue
        kind = i.meta.get("kind") if i.type in ("invalid_format", "inconsistent") else None
        groups[(i.type, i.column, kind)].append(i)
    out = []
    for (t, col, kind), items in groups.items():
        rows = sorted({i.row_id for i in items})
        if t in ("duplicate", "near_duplicate"):
            title = f"{len(rows)} {'exact' if t == 'duplicate' else 'likely'} duplicate rows"
        elif t == "anomaly":
            title = f"{len(rows)} unusual {col} values"
        else:
            title = f"{len(rows)} {_label(t, kind, col)}"
        sev = "low" if t == "anomaly" else "high" if t in HIGH or len(rows) > 0.01 * n_rows else "medium"
        out.append({"warning_id": "", "title": title, "explanation": f"e.g. row {items[0].row_id}: {items[0].message}",
                    "affected_rows": len(rows), "sample_row_ids": rows[:10], "suggested_action": ACTIONS.get(t, ""),
                    "severity": sev, "issue_type": t, "issue_kind": kind, "column": col})
    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda w: (order[w["severity"]], -w["affected_rows"]))
    for k, w in enumerate(out, 1):
        w["warning_id"] = f"W{k:02d}"
    return out


def heatmap(scan, n_rows: int, columns: list[str], blocks: int = 50) -> dict:
    blocks = max(1, min(blocks, n_rows))
    size = math.ceil(n_rows / blocks)
    cols = columns + ["(duplicates)"]
    counts = [[0] * len(cols) for _ in range(math.ceil(n_rows / size))]
    seen = set()
    for i in scan.issues:
        if i.row_id is None or i.type not in ERROR_TYPES | {"duplicate", "near_duplicate"}:
            continue
        c = cols.index(i.column) if i.column in columns else len(cols) - 1
        if (i.row_id, c) in seen:
            continue
        seen.add((i.row_id, c))
        counts[min(i.row_id // size, len(counts) - 1)][c] += 1
    cells = [[round(n / size, 4) for n in row] for row in counts]
    return {"columns": cols, "block_size": size, "cells": cells,
            "max": max((x for row in cells for x in row), default=0)}


def cell_states(s, table: str) -> dict[tuple[int, str], str]:
    key = ("states", table, s._version)
    cache = s.__dict__.setdefault("_ui_cache", {})
    if key in cache:
        return cache[key]
    st: dict[tuple[int, str], str] = {}
    for i in s.scans[table].issues:
        if i.row_id is not None and i.column and i.type in ERROR_TYPES:
            st[(i.row_id, i.column)] = "issue"
        elif i.row_id is not None and i.column and i.type == "anomaly":
            st.setdefault((i.row_id, i.column), "flagged")
    for p in s.proposals.values():
        if p.table == table and p.status == "pending" and p.column != ROW:
            st[(p.row_id, p.column)] = "review" if p.tier == "review" else "flagged" if p.tier in ("flag", "refused") \
                else st.get((p.row_id, p.column), "issue")
    for c in s.applied_changes(table):
        if c.column == ROW or c.algorithm == "privacy_drop":
            continue
        p = s.proposals.get(c.proposal_id or "")
        st[(c.row_id, c.column)] = "masked" if c.algorithm == "privacy_mask" else (
            "estimated" if p and p.repair_class == "impute" else "repaired")
    cache.clear()
    cache[key] = st
    return st


def rows_page(s, table: str, view: str = "current", offset: int = 0, limit: int = 100,
              issue_type: str | None = None, column: str | None = None, state: str | None = None,
              row_ids: list[int] | None = None) -> dict:
    limit = max(1, min(limit, 500))
    states = cell_states(s, table)
    orig = s.originals[table]
    df = orig if view == "original" else s.current(table)
    idx = list(df.index)
    if view == "diff":
        changed = {c.row_id for c in s.applied_changes(table) if c.column != ROW}
        idx = [r for r in idx if r in changed]
    if row_ids:
        wanted = set(row_ids)
        idx = [r for r in idx if r in wanted]
    if issue_type or column:
        hit = {i.row_id for i in s.scans[table].issues if i.row_id is not None
               and (not issue_type or i.type == issue_type) and (not column or i.column == column)}
        idx = [r for r in idx if r in hit]
    if state:
        hit = {r for (r, _), st in states.items() if st == state}
        idx = [r for r in idx if r in hit]
    page = idx[offset:offset + limit]
    cols = list(df.columns)
    rows = []
    for r in page:
        values = {c: df.at[r, c] for c in cols}
        cs = {c: states[(r, c)] for c in cols if (r, c) in states}
        originals = {c: orig.at[r, c] for c in cols if c in orig.columns and cs.get(c) in ("repaired", "estimated", "masked")}
        rows.append({"row_id": int(r), "values": values, "cell_state": cs, "original": originals})
    return {"total": len(idx), "offset": offset, "columns": cols, "rows": rows}


def row_detail(s, table: str, row_id: int) -> dict:
    cur = s.current(table)
    orig = s.originals[table]
    return {
        "row_id": row_id, "table": table, "deleted": row_id not in cur.index,
        "values": {c: cur.at[row_id, c] for c in cur.columns} if row_id in cur.index else None,
        "original": {c: orig.at[row_id, c] for c in orig.columns},
        "cell_state": {c: st for (r, c), st in cell_states(s, table).items() if r == row_id},
        "issues": [i.to_dict() for i in s.scans[table].issues if i.row_id == row_id],
        "proposals": [p.to_dict() for p in s.proposals.values() if p.table == table and p.row_id == row_id],
        "changes": [c.to_dict() for c in s.changes if c.table == table and c.row_id == row_id],
    }


def proposal_groups(s, tier: str | None = "review", column: str | None = None, limit: int = 50) -> list[dict]:
    """Bulk review by pattern: identical (column, from -> to) suggestions grouped, e.g. 23 × 'Bangalore' -> 'Bengaluru'."""
    groups: dict[tuple, list] = defaultdict(list)
    for p in s.proposals.values():
        if p.status != "pending" or (tier and p.tier != tier) or (column and p.column != column) or not p.candidates:
            continue
        frm = v.norm_key(p.original_value) if p.column != ROW else ""
        to = p.candidates[0].value if p.column != ROW else p.algorithm
        groups[(p.table, p.column, p.algorithm, frm, to)].append(p)
    out = []
    for (table, col, algo, frm, to), ps in groups.items():
        out.append({"table": table, "column": col, "algorithm": algo, "from": ps[0].original_value, "to": to,
                    "count": len(ps), "avg_confidence": round(sum(p.confidence for p in ps) / len(ps), 4),
                    "min_confidence": min(p.confidence for p in ps), "proposal_ids": [p.proposal_id for p in ps]})
    out.sort(key=lambda g: (-g["count"], -g["avg_confidence"]))
    return out[:limit]


def summary_counts(scan) -> dict:
    return dict(Counter(i.type for i in scan.issues if i.row_id is not None))
