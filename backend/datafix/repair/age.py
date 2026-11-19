"""Age repairs: compute it from the date of birth when the data proves that rule; number words; else estimate."""
import re

from .. import validators as v
from ..confidence import signal
from ..detect.crossfield import age_on, find_age_dob, learn_age_rule, parse_dob
from ..models import Issue
from . import RepairContext
from .impute import impute_numeric
from .outcome import Outcome, refuse

_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_age(x: str) -> int | None:
    parts = re.split(r"[\s-]+", x.strip().lower())
    if not parts or len(parts) > 2:
        return None
    if len(parts) == 1:
        n = _TENS.get(parts[0], _UNITS.get(parts[0]))
    else:
        n = _TENS.get(parts[0], 0) + _UNITS.get(parts[1], 0) if parts[0] in _TENS and parts[1] in _UNITS else None
    return n if n and 1 <= n <= 120 else None


def _rule(ctx: RepairContext):
    key = ("age_rule",)
    if key not in ctx.cache:
        cols = find_age_dob(ctx.scan.columns)
        rule = None
        if cols:
            a, d = cols
            ok_a = ctx.df[a].map(v.is_age) & ~ctx.df.index.map(lambda r: ctx.is_error(r, a)).to_numpy()
            ok_d = ctx.df[d].str.strip() != ""
            rule = learn_age_rule(ctx.df, a, d, ok_a, ok_d)
        ctx.cache[key] = (cols, rule)
    return ctx.cache[key]


def repair_age(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    raw = ctx.value(row, col).strip()
    (cols, rule) = _rule(ctx)
    words = words_to_age(raw)
    if rule and cols and cols[0] == col:
        dcol = cols[1]
        dob = parse_dob(ctx.value(row, dcol))
        if dob is not None and dob <= rule["ref"]:
            age = age_on(dob, rule["ref"])
            if 0 <= age <= 120:
                value = str(age)
                sigs = [signal("crossfield_rule", rule["agreement"],
                               f"{col} = whole years from {dcol} ({dob.isoformat()}) to {rule['ref'].isoformat()}; "
                               f"this holds for {rule['agreement']:.1%} of {rule['support']:,} rows")]
                conflict = any(i.meta.get("kind") == "age_dob" for i in issues)
                if not conflict:
                    sigs.append(signal("deterministic_transform", 1.0,
                                       f"{col} was {'blank' if not raw else repr(raw)}, so it is computed from {dcol}"))
                elif raw.isdigit() and raw[::-1].lstrip("0") == value:
                    sigs.append(signal("pattern_fix", 1.0, f"'{raw}' is '{value}' with its digits swapped"))
                if words is not None:
                    sigs.append(signal("deterministic_transform" if words == age else "crossfield_rule", 1.0,
                                       f"'{raw}' = {words}" + ("" if words == age else f", but {dcol} gives {age}"),
                                       conflicting=words != age))
                return Outcome("correct" if conflict else "recover", "age_from_dob", {value: sigs})
    if words is not None:
        return Outcome("normalize", "number_words", {str(words): [signal(
            "deterministic_transform", 1.0, f"'{raw}' written as a number")]})
    if any(i.meta.get("kind") == "age_dob" for i in issues):
        return refuse("correct", "age_from_dob", "age and date of birth disagree and the date could not be read")
    return impute_numeric(ctx, row, col, issues)
