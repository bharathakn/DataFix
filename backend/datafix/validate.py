"""Quality score, quality dimensions and do-no-harm validation (docs/05_ENGINE_SPEC.md §7)."""
from collections.abc import Iterable

import numpy as np
import pandas as pd

from . import validators as v
from .models import ROW_LEVEL_TYPES, Issue

DIMENSIONS = {
    "completeness": {"missing", "disguised_missing"},
    "validity": {"invalid_format"},
    "consistency": {"inconsistent", "fd_violation", "crossfield"},
    "uniqueness": {"duplicate", "near_duplicate"},
}
ERROR_TYPES = set().union(*DIMENSIONS.values())
PRIVACY_ALGOS = {"privacy_mask", "privacy_drop"}


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


def dimensions(issues: Iterable[Issue], n_rows: int) -> dict[str, float]:
    """Share of rows (%) free of each class of problem, plus fully clean rows.
    Row-based on purpose: cell-based ratios dilute 1,700 errors over ~200k cells into 99.x%."""
    rows: dict[str, set[int]] = {d: set() for d in DIMENSIONS}
    for i in issues:
        if i.row_id is None:
            continue
        for d, types in DIMENSIONS.items():
            if i.type in types:
                rows[d].add(i.row_id)
    out = {d: round(100 * (1 - len(r) / max(n_rows, 1)), 2) for d, r in rows.items()}
    out["clean_rows"] = round(100 * (1 - len(set().union(*rows.values())) / max(n_rows, 1)), 2)
    return out


def error_cells(issues: Iterable[Issue]) -> set[tuple[int, str]]:
    return {(i.row_id, i.column) for i in issues if i.row_id is not None and i.column and i.type in ERROR_TYPES}


def ks_statistic(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.sort(a), np.sort(b)
    grid = np.concatenate([a, b])
    return float(np.max(np.abs(np.searchsorted(a, grid, "right") / len(a) - np.searchsorted(b, grid, "right") / len(b))))


def _numbers(s: pd.Series, col_type: str) -> np.ndarray:
    parse = v.parse_money if col_type == "money" else (lambda x: float(x) if v.is_number(x) else None)
    vals = [parse(x) for x in s if x.strip()]
    return np.array([x for x in vals if x is not None], dtype=float)


def check_distributions(orig: pd.DataFrame, cur: pd.DataFrame, columns: dict,
                        canonical: dict[str, dict[str, str]] | None = None) -> tuple[bool, list[str]]:
    """Category shares are compared by meaning: original values go through the scan's canonical map first,
    so 'YES'/'y'/'1' -> 'true' or 'Bombay' -> 'Mumbai' is not a shift; a filled blank or a changed meaning is."""
    canonical = canonical or {}
    problems = []
    for col, info in columns.items():
        if col not in cur.columns:
            continue
        t = info.semantic_type
        if t in ("number", "money", "age"):
            a, b = _numbers(orig[col], t), _numbers(cur[col], t)
            if len(a) < 30 or len(b) < 30:
                continue
            med_a, med_b = np.median(a), np.median(b)
            rel = abs(med_b - med_a) / abs(med_a) if med_a else 0.0
            ks = ks_statistic(a, b)
            if rel > 0.05 or ks > 0.1:
                problems.append(f"{col}: median {med_a:g} → {med_b:g}, KS {ks:.3f}")
        elif t in ("category", "city", "state", "district"):
            before = set(orig[col].str.strip())
            new_values = set(cur[col].str.strip()) - before - {""}
            if new_values:
                problems.append(f"{col}: new categories {sorted(new_values)[:5]}")
            # total variation distance between category shares; robust to near-equal groups swapping rank
            cmap = canonical.get(col, {})
            key = lambda x: v.norm_key(cmap.get(x, x))
            pa = orig[col].map(key).value_counts(normalize=True)
            pb = cur[col].map(key).value_counts(normalize=True)
            tvd = 0.5 * pa.subtract(pb, fill_value=0).abs().sum()
            if tvd > 0.05:
                problems.append(f"{col}: category shares moved by {tvd:.1%} (TVD)")
    return not problems, problems


def orphans(main: pd.DataFrame, linked: pd.DataFrame, main_col: str, link_col: str) -> int:
    ids = set(main[main_col].str.strip())
    fk = linked[link_col].str.strip()
    return int((fk.ne("") & ~fk.isin(ids)).sum())
