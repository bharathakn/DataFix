"""Detectors share a ScanContext; run order matters (later detectors skip cells earlier ones marked unusable)."""
from dataclasses import dataclass, field

import pandas as pd

from ..models import ISSUE_WEIGHTS, ColumnInfo, Issue, LearnedRule
from ..reference import PinReference

CATEGORY_LIKE = {"category", "city", "state", "district", "locality"}


@dataclass
class ScanContext:
    df: pd.DataFrame
    columns: dict[str, ColumnInfo]
    ref: PinReference | None
    blank: dict[str, pd.Series] = field(default_factory=dict)
    unusable: dict[str, pd.Series] = field(default_factory=dict)  # blank or disguised placeholder
    invalid: dict[str, pd.Series] = field(default_factory=dict)  # fails its column's validator
    canonical: dict[str, dict[str, str]] = field(default_factory=dict)  # raw value -> canonical form
    sparse: set[str] = field(default_factory=set)
    issues: list[Issue] = field(default_factory=list)
    rules: list[LearnedRule] = field(default_factory=list)
    # rule_id -> {lhs, rhs, confidence, groups: {lhs_key: {value, key, share, size}}}
    fd_maps: dict[str, dict] = field(default_factory=dict)
    _seen: set = field(default_factory=set)

    def add(self, row: int | None, col: str | None, type_: str, detector: str, message: str,
            value: str | None = None, **meta) -> None:
        key = (row, col, type_)
        if key in self._seen:
            return
        self._seen.add(key)
        self.issues.append(Issue("", None if row is None else int(row), col, type_,
                                 ISSUE_WEIGHTS.get(type_, 0.4), detector, message, value, meta))

    def flagged_cells(self, types: set[str] | None = None) -> set[tuple[int, str]]:
        return {(i.row_id, i.column) for i in self.issues
                if i.row_id is not None and i.column and (types is None or i.type in types)}

    def usable(self, col: str) -> pd.Series:
        bad = self.unusable[col]
        if col in self.invalid:
            bad = bad | self.invalid[col]
        return ~bad
