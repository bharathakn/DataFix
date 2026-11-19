"""Do-no-harm validation of a session's repaired data (docs/05_ENGINE_SPEC.md §7.2)."""
import time

from .planner import plan_repairs
from .repair import find_joins
from .scan import scan_table
from .validate import (DIMENSIONS, PRIVACY_ALGOS, check_distributions, dimensions, error_cells, orphans,
                       quality_score)

ROW = "__row__"


def _check(name: str, passed: bool, value, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "value": str(value), "detail": detail}


def validate_session(s) -> dict:
    t0 = time.perf_counter()
    main = s.main
    orig, cur = s.originals[main], s.current(main)
    scan0 = s.scans[main]
    rescans = {n: scan_table(s.current(n), n, columns={c: i for c, i in s.scans[n].columns.items()
                                                       if c in s.current(n).columns}) for n in s.originals}
    scan1 = rescans[main]
    applied = s.applied_changes()
    cell_changes = [c for c in applied if c.column != ROW and c.algorithm not in PRIVACY_ALGOS]
    checks = []

    # 1. valid values changed: a non-blank cell with no detected issue was altered
    flagged = {(n, r, c) for n, sc in s.scans.items() for (r, c) in error_cells(sc.issues)}
    harmed = [c for c in cell_changes
              if (c.table, c.row_id, c.column) not in flagged and c.original_value.strip() != ""
              and not c.reason.startswith("re-pointed")]
    checks.append(_check("valid_cells_changed", not harmed, len(harmed),
                         "non-blank cells changed without a detected issue (target 0)"
                         + (f": {[(c.table, c.row_id, c.column) for c in harmed[:5]]}" if harmed else "")))

    # 2. schema
    dropped_cols = set(s.dropped_columns(main))
    expected_cols = [c for c in orig.columns if c not in dropped_cols]
    checks.append(_check("schema_unchanged", list(cur.columns) == expected_cols, f"{len(cur.columns)} columns",
                         "same columns in the same order" + (f" (privacy-dropped: {sorted(dropped_cols)})"
                                                             if dropped_cols else "")))

    # 3. row count explained by merges
    removed = len(orig) - len(cur)
    merges = sum(1 for c in applied if c.column == ROW and c.table == main)
    checks.append(_check("row_count_explained", removed == merges, f"-{removed} rows",
                         f"{merges} duplicate merges explain {removed} removed rows"))

    # 4. distributions
    ok, problems = check_distributions(orig, cur, scan0.columns)
    checks.append(_check("distribution_stable", ok, "stable" if ok else f"{len(problems)} shifts",
                         "numeric medians within 5% and KS < 0.1; no new categories; category shares move < 5% (TVD)"
                         + (f": {problems[:3]}" if problems else "")))

    # 5. no new errors on cells DataFix changed; errors surfacing on untouched cells are reported separately
    before_cells = error_cells(scan0.issues)
    masked = {(c.row_id, c.column) for c in applied if c.table == main and c.algorithm in PRIVACY_ALGOS}
    # masked values (98XXXXXX45, ABCPX****Q) fail their validators by design: not a quality problem
    issues1 = [i for i in scan1.issues if (i.row_id, i.column) not in masked]
    after_cells = error_cells(issues1)
    changed = {(c.row_id, c.column) for c in cell_changes if c.table == main}
    introduced = sorted((after_cells - before_cells) & changed)
    surfaced = sorted((after_cells - before_cells) - changed)
    still = sorted(after_cells & changed)
    checks.append(_check("no_new_errors", not introduced, len(introduced),
                         f"repaired cells that now fail a check (target 0); {len(surfaced)} pre-existing problems "
                         f"surfaced once neighbouring errors were fixed"))

    # 6. referential integrity across linked tables
    orphan_before = orphan_after = 0
    for n in s.originals:
        if n == main:
            continue
        for mc, lc in find_joins(scan0, s.scans[n]):
            if scan0.columns[mc].semantic_type != "id":
                continue
            orphan_before += orphans(orig, s.originals[n], mc, lc)
            orphan_after += orphans(cur, s.current(n), mc, lc)
    checks.append(_check("referential_integrity", orphan_after <= orphan_before, orphan_after,
                         f"linked records pointing to a missing {main} row (before: {orphan_before})"))

    # 7. idempotent: planning again on the repaired data proposes no further automatic fixes
    replan = plan_repairs({n: s.current(n) for n in s.originals}, rescans, s.thresholds)
    # not counted: cells the user masked on purpose, and cells/rows whose repair the user rejected or undid
    # (and items still open in the review queue: e.g. hashing phones turns pending near-duplicates into exact ones)
    declined = {(p.table, p.row_id, p.column) for p in s.proposals.values()
                if p.status in ("rejected", "undone") or (p.status == "pending" and p.tier != "auto")}
    again = [p for p in replan if p.tier == "auto" and not (p.table == main and (p.row_id, p.column) in masked)
             and (p.table, p.row_id, p.column) not in declined]
    checks.append(_check("idempotent", not again, len(again),
                         "high-confidence fixes proposed when DataFix runs on its own output (target 0)"
                         + (f": {sorted({(p.column, p.algorithm) for p in again})[:5]}" if again else "")))

    # 8. audit chain
    audit = s.verify_audit()
    checks.append(_check("audit_chain_valid", audit["valid"], f"{audit['entries']} entries",
                         f"hash chain verified from the input files' SHA-256; head {audit['head_hash'][:12]}"))

    tiers = {t: sum(1 for p in s.proposals.values() if p.tier == t and p.status == "pending")
             for t in ("review", "flag", "refused")}
    return {
        "score_before": quality_score(scan0.issues, len(orig), len(orig.columns)),
        "score_after": quality_score(issues1, len(cur), len(orig.columns)),
        "dimensions_before": dimensions(scan0.issues, len(orig)),
        "dimensions_after": dimensions(issues1, len(cur)),
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
        "unresolved": tiers,
        "remaining_errors": len(after_cells) + sum(1 for i in issues1 if i.type in DIMENSIONS["uniqueness"]),
        "still_failing_after_repair": len(still),
        "surfaced": len(surfaced),
        "duration_ms": int((time.perf_counter() - t0) * 1000),
    }
