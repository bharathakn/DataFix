from dataclasses import asdict, dataclass, field
from typing import Any

# Severity weight per issue type, used by the quality score (docs/05_ENGINE_SPEC.md §4).
ISSUE_WEIGHTS: dict[str, float] = {
    "missing": 0.7,
    "disguised_missing": 0.7,
    "duplicate": 1.0,
    "near_duplicate": 1.0,
    "invalid_format": 0.4,
    "inconsistent": 0.4,
    "fd_violation": 0.8,
    "crossfield": 0.8,
    "anomaly": 0.2,
    "sparse_column": 0.0,
}
ROW_LEVEL_TYPES = {"duplicate", "near_duplicate"}


@dataclass
class ColumnInfo:
    name: str
    semantic_type: str
    type_confidence: float
    null_count: int = 0
    distinct: int = 0
    sample: list[str] = field(default_factory=list)
    overridden: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Issue:
    issue_id: str
    row_id: int | None
    column: str | None
    type: str
    severity_weight: float
    detector: str
    message: str
    value: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LearnedRule:
    rule_id: str
    kind: str  # fd | crossfield | user
    lhs: str
    rhs: str
    description: str
    support: int
    confidence: float
    violations: int = 0
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)
