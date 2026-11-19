"""Reusable cleaning recipe (docs/05_ENGINE_SPEC.md §10): the approved steps as data, not row numbers.
Replaying a recipe on a new file (`datafix apply`) is a stretch item; the export already captures everything needed."""
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROW = "__row__"


def build_recipe(s) -> dict:
    main = s.main
    steps: list[dict] = []
    counts: Counter = Counter()
    value_maps: dict[str, dict[str, str]] = defaultdict(dict)
    for p in s.proposals.values():
        if p.status != "applied" or p.table != main:
            continue
        if p.column == ROW:
            counts[("dedupe", p.algorithm)] += 1
        elif p.algorithm == "standardize" or (p.repair_class == "correct" and p.algorithm == "standardize"):
            value_maps[p.column][p.original_value] = p.meta.get("applied_value", "")
        elif p.repair_class == "correct" and p.algorithm == "fd_repair":
            counts[("fd_repair", p.column)] += 1
        else:
            counts[(p.algorithm, p.column)] += 1
    for col, mapping in sorted(value_maps.items()):
        steps.append({"op": "map_values", "column": col, "map": dict(sorted(mapping.items()))})
    for (algo, col), n in sorted(counts.items()):
        if algo == "dedupe":
            steps.append({"op": "dedupe", "method": col, "survivor": "earliest_row", "fill_blanks_from_duplicate": True,
                          "remap_foreign_keys": True, "applied": n})
        elif algo == "fd_repair":
            steps.append({"op": "fd_repair", "column": col, "applied": n})
        else:
            steps.append({"op": algo, "column": col, "applied": n})
    for c in s.changes:
        if c.action == "apply" and c.status == "applied" and c.algorithm in ("privacy_mask", "privacy_drop"):
            step = {"op": "privacy", "column": c.column, "method": "drop" if c.algorithm == "privacy_drop"
                    else c.reason.rsplit(" ", 1)[-1]}
            if step not in steps:
                steps.append(step)
    scan = s.scans[main]
    return {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": s.files[main],
        "column_types": {c: i.semantic_type for c, i in scan.columns.items()},
        "thresholds": s.thresholds or {"auto": 0.95, "review": 0.70},
        "learned_rules": [{"lhs": r.lhs, "rhs": r.rhs, "kind": r.kind, "confidence": r.confidence}
                          for r in scan.rules],
        "steps": steps,
    }
