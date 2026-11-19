"""PIN recovery (docs/05_ENGINE_SPEC.md §5.5): one-digit edits, India Post reference, row context, locality."""
import re

from rapidfuzz import fuzz

from .. import validators as v
from ..confidence import signal
from ..models import Issue, Signal
from . import RepairContext
from .category import similar_place
from .outcome import Outcome, refuse


def one_digit_edits(p: str) -> set[str]:
    p = "".join(ch for ch in p if ch.isdigit())
    out = set()
    if len(p) == 5:
        out |= {p[:i] + d + p[i:] for i in range(6) for d in "0123456789"}
    elif len(p) == 7:
        out |= {p[:i] + p[i + 1:] for i in range(7)}
    elif len(p) == 6:
        out |= {p[:i] + d + p[i + 1:] for i in range(6) for d in "0123456789"} - {p}
        out |= {p[:i] + p[i + 1] + p[i] + p[i + 2:] for i in range(5)}  # adjacent swap
    return {c for c in out if v.is_pin_format(c)}


def repair_pin(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    if ctx.ref is None:
        return refuse("recover", "pin_recovery", "no PIN reference loaded")
    raw = ctx.value(row, col).strip()
    city = _first_trusted(ctx, row, "city")
    district = _first_trusted(ctx, row, "district")
    state = _first_trusted(ctx, row, "state")
    locality = _first_trusted(ctx, row, "locality")
    votes = ctx.fd_votes(row, col)

    pool = one_digit_edits(raw) if raw else set()
    pool |= set(votes)
    valid = sorted(c for c in pool if c in ctx.ref)
    cands: dict[str, list[Signal]] = {}
    n_ctx = n_loc = 0
    for c in valid:
        offices = ctx.ref.lookup(c)
        sigs: list[Signal] = []
        place = city or district
        if place:
            names = {o["district"] for o in offices} | {o["city"] for o in offices if o["city"]}
            if any(similar_place(place, n) for n in names):
                n_ctx += 1
                sigs.append(signal("row_context", 1.0, f"PIN {c} is in {sorted(names)[0]}, matching this row's "
                                                       f"{'city' if city else 'district'} '{place}'"))
        if state and not any(similar_place(state, o["state"]) for o in offices):
            sigs.append(signal("row_context", 1.0, f"PIN {c} is in {offices[0]['state']}, not {state}", True))
        if locality:
            lk = v.office_key(locality)
            hit = next((o["office"] for o in offices if _same_place(v.office_key(o["office"]), lk)), None)
            if hit:
                n_loc += 1
                sigs.append(signal("locality_match", 1.0, f"PIN {c} serves the post office '{hit}' = locality "
                                                          f"'{locality}'"))
        sigs.extend(votes.get(c, []))
        if any(not s.conflicting for s in sigs):
            cands[c] = sigs

    summary = (f"{len(valid)} valid PINs are one digit from '{raw}'" if raw else "PIN is missing") + \
              (f"; {n_ctx} are in {city or district}" if (city or district) else "") + \
              (f"; {n_loc} {'serves' if n_loc == 1 else 'serve'} '{locality}'" if locality else "")
    if not cands:
        return refuse("recover", "pin_recovery", f"{summary}; none is supported by this row's address",
                      valid_candidates=len(valid))
    for sigs in cands.values():
        sigs.insert(0, signal("reference_pin", 0.0, summary))  # explanatory, adds no weight
    return Outcome("recover", "pin_recovery", cands,
                   meta={"valid_candidates": len(valid), "in_place": n_ctx, "in_locality": n_loc})


def _same_place(a: str, b: str) -> bool:
    """Fuzzy on letters, exact on numbers: 'Sector 12' is not 'Sector 21'."""
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    return fuzz.ratio(a, b) >= 90


def _first_trusted(ctx: RepairContext, row: int, sem_type: str) -> str | None:
    for c in ctx.cols_of_type(sem_type):
        x = ctx.trusted(row, c)
        if x:
            return x
    return None
