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


@dataclass
class Signal:
    name: str
    score: float  # 0..1 strength of this evidence
    reliability: float  # 0..1 prior trust in this kind of evidence
    detail: str  # human sentence
    conflicting: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Candidate:
    value: str
    confidence: float
    signals: list[Signal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepairProposal:
    proposal_id: str
    table: str
    issue_ids: list[str]
    row_id: int
    column: str  # "__row__" for duplicate merges
    original_value: str
    candidates: list[Candidate]
    tier: str  # auto | review | flag | refused
    repair_class: str  # normalize | standardize | correct | recover | impute | dedupe_merge | none
    algorithm: str
    refusal_reason: str | None = None
    status: str = "pending"  # pending | applied | rejected | undone
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        return self.candidates[0].confidence if self.candidates else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = self.confidence
        return d


@dataclass
class Change:
    """One audit-log entry. action=apply changes a cell; undo/redo/reject reference an earlier entry.
    Every field except `status` and `hash` is covered by the hash chain; status is derived state."""
    change_id: str
    checkpoint_id: str
    proposal_id: str | None
    table: str
    row_id: int
    column: str  # "__row__" for a row removal
    original_value: str
    new_value: str
    reason: str
    evidence: list[str]
    source: str
    confidence: float
    algorithm: str
    actor: str  # auto | user | chat | system
    action: str  # apply | undo | redo | reject
    target: str | None  # change_id that an undo/redo refers to
    timestamp: str
    prev_hash: str = ""
    hash: str = ""
    status: str = "applied"  # applied | undone (only meaningful for action=apply)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Checkpoint:
    checkpoint_id: str
    label: str
    kind: str  # original | auto | review | bulk | mask | user
    change_ids: list[str]
    created_at: str
    quality_score: float

    def to_dict(self) -> dict:
        return asdict(self)
