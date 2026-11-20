"""Phone and email recovery: Excel notation, linked tables, common typing mistakes."""
import re
from collections import Counter

from .. import validators as v
from ..confidence import signal
from ..models import Issue, Signal
from . import RepairContext
from .outcome import Outcome, refuse

KNOWN_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "rediffmail.com",
                 "icloud.com", "live.com", "protonmail.com"}


def _linked(ctx: RepairContext, row: int, sem_type: str, partial: str | None, cands: dict[str, list[Signal]]):
    """Add linked-table evidence; return a refusal reason if the linked data conflicts."""
    for table, counts, how in ctx.linked_values(row, sem_type):
        if not counts:
            continue
        if len(counts) > 1:
            shown = ", ".join(_mask(x, sem_type) for x in list(counts)[:3])
            return f"{len(counts)} different {sem_type}s found in {table} for {how} ({shown}); DataFix won't guess"
        value, n = next(iter(counts.items()))
        sigs = cands.setdefault(value, [])
        sigs.append(signal("linked_table_match", 1.0, f"{table} has {sem_type} {_mask(value, sem_type)} for {how}"))
        if n >= 2:
            sigs.append(signal("records_agree", 1.0, f"all {n} matching {table} records agree"))
        if partial and len(partial) >= 5 and partial in value:
            sigs.append(signal("prefix_match", 1.0, f"the remaining digits '{partial}' are part of {_mask(value, sem_type)}"))
    return None


def _mask(x: str, sem_type: str) -> str:
    return f"{x[:2]}XXXXXX{x[-2:]}" if sem_type == "phone" and len(x) == 10 else x


def repair_phone(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col).strip()
    kinds = {i.meta.get("kind") for i in issues}
    cands: dict[str, list[Signal]] = {}
    partial = None
    if "excel_scientific_notation" in kinds:
        mantissa = re.sub(r"\D", "", raw.split("E")[0].split("e")[0])
        if len(mantissa) >= 10:
            value = str(int(float(raw)))
            if v.is_phone(value):
                cands[value] = [signal("deterministic_transform", 1.0,
                                       f"'{raw}' is scientific notation with all 10 digits intact")]
        partial = mantissa
    elif raw and raw.isdigit():
        partial = raw
    conflict = _linked(ctx, row, "phone", partial, cands)
    if conflict and not cands:
        return refuse("recover", "phone_recovery", conflict)
    if not cands:
        if "excel_scientific_notation" in kinds:
            return refuse("recover", "phone_recovery",
                          f"Excel kept only {len(partial or '')} of 10 digits and no linked record has this phone")
        return refuse("recover", "phone_recovery", "no linked record holds a phone for this row")
    return Outcome("recover", "phone_recovery", cands)


def repair_email(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col).strip()
    cands: dict[str, list[Signal]] = {}
    if raw != ctx.value(row, col) and v.is_email(raw):
        cands[raw] = [signal("deterministic_transform", 1.0, "removed stray spaces; no characters changed")]
    domains = _column_domains(ctx, col)
    for fixed, how in _email_fixes(raw, domains):
        cands.setdefault(fixed, []).append(signal("pattern_fix", 1.0, f"common typo: {how}"))
        dom = fixed.split("@")[1]
        if dom in domains or dom in KNOWN_DOMAINS:
            cands[fixed].append(signal("known_domain", 1.0, f"'{dom}' is a real, common domain"))
    conflict = _linked(ctx, row, "email", None, cands)
    if conflict and not cands:
        return refuse("recover", "email_recovery", conflict)
    if not cands:
        return refuse("recover", "email_recovery", "no linked record or safe typo fix for this email")
    return Outcome("recover" if not raw or raw.casefold() in ("test@test.com",) else "correct",
                   "email_recovery", cands)


def _column_domains(ctx: RepairContext, col: str) -> set[str]:
    key = ("domains", col)
    if key not in ctx.cache:
        doms = Counter(x.split("@")[-1].strip().casefold() for x in ctx.df[col] if v.is_email(x))
        ctx.cache[key] = {d for d, n in doms.items() if n >= 20}
    return ctx.cache[key]


def _email_fixes(raw: str, domains: set[str]) -> list[tuple[str, str]]:
    if not raw or "@" not in raw and not any(raw.casefold().endswith(d) for d in domains | KNOWN_DOMAINS):
        return []
    out = []
    s = raw.strip()
    if " " in s:
        t = s.replace(" ", "")
        if v.is_email(t):
            out.append((t.casefold(), "removed a space"))
    if "@@" in s:
        t = re.sub("@+", "@", s)
        if v.is_email(t):
            out.append((t.casefold(), "removed a doubled '@'"))
    if "@" in s:
        local, dom = s.rsplit("@", 1)
        for d in domains | KNOWN_DOMAINS:
            if "." not in dom and d.replace(".", "") == dom.casefold():
                out.append((f"{local}@{d}".casefold(), f"restored the missing dot in '{d}'"))
    else:
        for d in sorted(domains | KNOWN_DOMAINS, key=len, reverse=True):
            if s.casefold().endswith(d) and len(s) > len(d):
                local = s[:-len(d)]
                # 'priya.shah.example.com': the '@' was typed as a dot, so that dot goes
                local = local[:-1] if local.endswith(".") else local
                if local and not local.endswith(".") and v.is_email(f"{local}@{d}"):
                    out.append((f"{local}@{d}".casefold(), f"restored the missing '@' before '{d}'"))
                break
    return out
