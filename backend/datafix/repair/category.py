"""Category / city-like cells: variants, aliases, spelling, learned-rule violations and missing values."""
from collections import Counter

from rapidfuzz import fuzz

from .. import validators as v
from ..confidence import signal
from ..knowledge import CITY_ALIASES
from ..models import Issue, Signal
from . import RepairContext
from .outcome import Outcome, refuse

KIND_SIGNAL = {
    "whitespace": ("format_variant", "same value with stray spaces removed"),
    "variant": ("format_variant", "same value written with different case/punctuation; most common form chosen"),
    "alias": ("alias_dictionary", "known alternate / old name"),
    "synonym": ("format_variant", "same meaning written in another style; the column's most common form chosen"),
}


def repair_category(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col)
    types = {i.type for i in issues}
    cands: dict[str, list[Signal]] = {}

    def add(value: str, sig: Signal):
        cands.setdefault(value, []).append(sig)

    # 1) what consistency detection suggested
    for i in issues:
        if i.type != "inconsistent":
            continue
        kind, sugg = i.meta.get("kind"), i.meta.get("suggestion")
        if not sugg:
            continue
        if kind in KIND_SIGNAL:
            name, text = KIND_SIGNAL[kind]
            add(sugg, signal(name, 1.0, f"'{raw}' → '{sugg}': {text}"))
        elif kind == "spelling":
            sim = i.meta.get("similarity", 0) / 100
            add(sugg, signal("string_similarity", sim,
                             f"'{raw}' is {sim:.0%} similar to '{i.meta.get('similar_to')}'"))
            freq = _frequency_share(ctx, col, raw, sugg)
            if freq:
                add(sugg, signal("vocab_frequency", freq,
                                 f"'{sugg}' is far more common in {col} than '{raw}'"))
            alias_target = CITY_ALIASES.get(v.norm_key(i.meta.get("similar_to", "")))
            if alias_target:
                add(sugg, signal("alias_dictionary", 1.0,
                                 f"'{i.meta.get('similar_to')}' is a known alternate name of '{alias_target}'"))

    # 2) learned rules from other columns in this row
    votes = ctx.fd_votes(row, col)
    for value, sigs in votes.items():
        for s in sigs:
            add(value, s)

    # 3) learned rules that disagree with a suggestion are conflicting evidence
    if votes:
        for value in list(cands):
            if value not in votes:
                for other, sigs in votes.items():
                    cands[value].append(Signal("fd_majority", sigs[0].score, sigs[0].reliability,
                                               f"conflict: {sigs[0].detail}", True))
                    break

    cands.pop(raw, None)  # keeping the current value is not a repair

    algo = "fd_repair" if "fd_violation" in types else (
        "fill_from_rules" if types & {"missing", "disguised_missing"} else "standardize")
    cls = "correct" if "fd_violation" in types or any(i.meta.get("kind") == "spelling" for i in issues) else (
        "recover" if algo == "fill_from_rules" else "standardize")
    if not cands:
        if algo == "fill_from_rules":
            return refuse("recover", algo, f"no learned rule or reference determines {col} for this row")
        return refuse(cls, algo, "no candidate value with supporting evidence")
    return Outcome(cls, algo, cands)


def _frequency_share(ctx: RepairContext, col: str, raw: str, target: str) -> float:
    key = ("vocab", col)
    if key not in ctx.cache:
        ctx.cache[key] = Counter(ctx.df[col].str.strip())
    counts = ctx.cache[key]
    t, r = counts.get(target, 0), counts.get(raw.strip(), 0)
    return t / (t + r) if t else 0.0


def similar_place(a: str, b: str) -> bool:
    """City vs district/city names, alias- and spelling-tolerant ('Bengaluru' ~ 'BENGALURU URBAN' ~ 'Bangalore')."""
    ka, kb = v.norm_key(a), v.norm_key(b)
    if not ka or not kb:
        return False
    ka = v.norm_key(CITY_ALIASES.get(ka, ka))
    kb = v.norm_key(CITY_ALIASES.get(kb, kb))
    return ka == kb or ka in kb.split() or kb in ka.split() or fuzz.ratio(ka, kb) >= 85
