"""Evidence combination and tiering (docs/05_ENGINE_SPEC.md §5.1).

conf = 1 − Π(1 − r·s) over supporting signals, × Π(1 − r·s) over conflicting ones, capped per repair class.
Independent agreeing evidence raises confidence quickly; any conflict pulls it down.
"""
from .models import Candidate, Signal

RELIABILITY = {
    "deterministic_transform": 0.99,
    "format_variant": 0.97,
    "reference_pin": 0.97,
    "alias_dictionary": 0.95,
    "locality_match": 0.95,
    "linked_table_match": 0.92,
    "fd_majority": 0.90,
    "prefix_match": 0.90,
    "crossfield_rule": 0.90,
    "row_context": 0.85,
    "pattern_fix": 0.85,
    "string_similarity": 0.70,
    "records_agree": 0.60,
    "known_domain": 0.60,
    "group_statistic": 0.85,
    "record_match": 0.95,
    "vocab_frequency": 0.50,
    "abbreviation": 0.80,
}

CAPS = {"impute": 0.85, "near_duplicate": 0.94, "distinct_id_duplicate": 0.94}
DEFAULT_CAP = 0.99
DEFAULT_THRESHOLDS = {"auto": 0.95, "review": 0.70}


def signal(name: str, score: float, detail: str, conflicting: bool = False) -> Signal:
    return Signal(name, round(max(0.0, min(score, 1.0)), 4), RELIABILITY[name], detail, conflicting)


def combine(signals: list[Signal], cap: float = 1.0) -> float:
    support = 1.0
    penalty = 1.0
    for s in signals:
        if s.conflicting:
            penalty *= 1 - s.reliability * s.score
        else:
            support *= 1 - s.reliability * s.score
    return round(min((1 - support) * penalty, cap), 4)


def rank(cands: dict[str, list[Signal]], cap: float = DEFAULT_CAP, limit: int = 3) -> list[Candidate]:
    """Score candidates; if the runner-up is nearly as strong, the choice is ambiguous -> cap below auto."""
    # rank on uncapped strength so extra evidence still breaks ties between capped candidates
    scored = sorted(((combine(sig), v, sig) for v, sig in cands.items() if sig), key=lambda t: -t[0])
    out = [Candidate(v, round(min(raw, cap), 4), sig) for raw, v, sig in scored]
    if len(out) >= 2 and out[1].confidence >= out[0].confidence - 0.05:
        top = out[0]
        top.signals.append(Signal("ambiguous", 1.0, 0.0,
                                  f"'{out[1].value}' is almost as likely ({out[1].confidence:.0%})", True))
        top.confidence = min(top.confidence, 0.85)
    return out[:limit]


def tier_for(conf: float, thresholds: dict | None = None) -> str:
    t = thresholds or DEFAULT_THRESHOLDS
    if conf >= t["auto"]:
        return "auto"
    if conf >= t["review"]:
        return "review"
    return "flag"
