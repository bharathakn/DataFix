from dataclasses import dataclass, field

from ..models import Signal


@dataclass
class Outcome:
    repair_class: str
    algorithm: str
    candidates: dict[str, list[Signal]] = field(default_factory=dict)
    refusal: str | None = None
    cap_key: str | None = None  # key into confidence.CAPS
    meta: dict = field(default_factory=dict)


def refuse(repair_class: str, algorithm: str, reason: str, **meta) -> Outcome:
    return Outcome(repair_class, algorithm, refusal=reason, meta=meta)
