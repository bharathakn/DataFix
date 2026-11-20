"""Deterministic normalisation: encoding damage, whitespace, case, date and money formats."""
from collections import Counter

from .. import validators as v
from ..confidence import signal
from ..models import Issue
from . import RepairContext
from .outcome import Outcome, refuse


def fix_encoding(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col)
    for wrong in ("latin-1", "cp1252"):
        try:
            fixed = raw.encode(wrong).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed != raw and not v.has_mojibake(fixed):
            return Outcome("normalize", "encoding_roundtrip", {fixed: [signal(
                "deterministic_transform", 1.0,
                f"UTF-8 text was read as {wrong}; re-decoding gives '{fixed}' with no garbled characters")]})
    return refuse("normalize", "encoding_roundtrip", "garbled text could not be decoded back reliably")


def fix_text(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col)
    kinds = {i.meta.get("kind") for i in issues}
    fixed = " ".join(raw.split())
    sigs = []
    if fixed != raw:
        sigs.append(signal("deterministic_transform", 1.0, "removed stray spaces; no characters changed"))
    if "case" in kinds:
        fixed = fixed.title()
        sigs.append(signal("format_variant", 0.98, "converted to the Title Case used by the rest of the column"))
    if fixed == raw:
        return refuse("normalize", "text_normalize", "no safe normalisation found")
    return Outcome("normalize", "text_normalize", {fixed: sigs})


def _dominant_format(ctx: RepairContext, col: str, family: str) -> str | None:
    key = ("date_fmt", col)
    if key not in ctx.cache:
        sample = ctx.df[col].head(3000)
        counts = Counter()
        for x in sample:
            for fmt, fam in v.DATE_FORMATS.items():
                if fam != family:
                    continue
                if v.parse_date_exact(x, fmt):
                    counts[fmt] += 1
        ctx.cache[key] = counts.most_common(1)[0][0] if counts else None
    return ctx.cache[key]


def fix_date(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col)
    issue = next(i for i in issues if i.meta.get("kind") == "date_format")
    dominant, found = issue.meta["dominant"], issue.meta["found"]
    fmt = _dominant_format(ctx, col, dominant)
    if fmt is None:
        return refuse("normalize", "date_reformat", "could not determine the column's date format")
    if len(found) != 1:
        # day and month both <= 12: each reading is a real date. Offer both for a human to pick.
        cands = {}
        for fam in sorted(found):  # dmy before mdy
            d = v.parse_date(raw, prefer=fam)
            if d is not None and d.strftime(fmt) not in cands:
                cands[d.strftime(fmt)] = [signal(
                    "format_variant", 0.8, f"'{raw}' read as {fam.upper()}; the other reading is also a real date, "
                    "so a person has to choose")]
        if not cands:
            return refuse("normalize", "date_reformat", "date is ambiguous between formats")
        return Outcome("normalize", "date_reformat", cands)
    d = v.parse_date(raw, prefer=found[0])
    if d is None:
        return refuse("normalize", "date_reformat", "could not determine the column's date format")
    fixed = d.strftime(fmt)
    why = (f"'{raw}' is the same {dominant.upper()} date written with different separators"
           if issue.meta.get("same_family") else
           f"'{raw}' is only a valid date as {found[0].upper()} (month > 12 otherwise)")
    return Outcome("normalize", "date_reformat", {fixed: [signal(
        "deterministic_transform", 1.0, f"{why}; rewritten in the column's {dominant.upper()} format")]})


def fix_money(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col)
    issue = next(i for i in issues if i.meta.get("kind") == "money_format")
    amount = v.parse_money(raw)
    if amount is None or issue.meta.get("dominant") != "plain":
        return refuse("normalize", "money_normalize", "amount format could not be converted safely")
    fixed = str(int(round(amount))) if abs(amount - round(amount)) < 1e-6 * max(1, abs(amount)) else f"{amount:.2f}"
    return Outcome("normalize", "money_normalize", {fixed: [signal(
        "deterministic_transform", 1.0, f"'{raw}' = {fixed} rupees, written as a plain number like the rest of {col}")]})
