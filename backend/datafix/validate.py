"""Quality score (docs/05_ENGINE_SPEC.md §7.1). Do-no-harm checks arrive in Phase 3."""
from collections.abc import Iterable

from .models import ROW_LEVEL_TYPES, Issue


def quality_score(issues: Iterable[Issue], n_rows: int, n_cols: int) -> float:
    """Q = 100 × (1 − Σ max_weight(cell) / N_cells); a duplicate row weighs 1.0 on every cell."""
    n_cells = n_rows * n_cols
    if n_cells == 0:
        return 100.0
    cell_w: dict[tuple[int, str], float] = {}
    dup_rows: set[int] = set()
    for i in issues:
        if i.row_id is None:
            continue
        if i.type in ROW_LEVEL_TYPES:
            dup_rows.add(i.row_id)
        elif i.column is not None and i.severity_weight > 0:
            k = (i.row_id, i.column)
            cell_w[k] = max(cell_w.get(k, 0.0), i.severity_weight)
    penalty = sum(w for (r, _), w in cell_w.items() if r not in dup_rows) + len(dup_rows) * n_cols
    return round(100 * (1 - penalty / n_cells), 2)
