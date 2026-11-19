"""Group-median imputation for numeric columns like age. Always an estimate, never auto-applied."""
import pandas as pd

from .. import validators as v
from ..confidence import signal
from ..models import Issue
from . import RepairContext
from .outcome import Outcome, refuse

MIN_GROUP = 5
MAX_IQR = 15.0


def _numeric(ctx: RepairContext, col: str) -> pd.Series:
    key = ("num", col)
    if key not in ctx.cache:
        valid = [(r, float(x)) for r, x in ctx.df[col].items()
                 if not ctx.is_error(r, col) and v.is_age(x)]
        ctx.cache[key] = pd.Series(dict(valid), dtype=float)
    return ctx.cache[key]


def _best_grouping(ctx: RepairContext, col: str) -> str | None:
    """The category column whose groups have the tightest spread of this value."""
    key = ("groupby", col)
    if key in ctx.cache:
        return ctx.cache[key]
    vals = _numeric(ctx, col)
    best, best_iqr = None, float("inf")
    for g in ctx.cols_of_type("category", "city", "state", "district"):
        info = ctx.scan.columns[g]
        if g == col or not 2 <= info.distinct <= 50:
            continue
        groups = ctx.df[g].loc[vals.index]
        stats = vals.groupby(groups).agg(["count", lambda s: s.quantile(0.75) - s.quantile(0.25)])
        stats.columns = ["n", "iqr"]
        stats = stats[stats["n"] >= MIN_GROUP]
        if stats.empty:
            continue
        w_iqr = (stats["iqr"] * stats["n"]).sum() / stats["n"].sum()
        if w_iqr < best_iqr:
            best, best_iqr = g, w_iqr
    overall = vals.quantile(0.75) - vals.quantile(0.25)
    ctx.cache[key] = best if best is not None and best_iqr < 0.8 * overall else None
    return ctx.cache[key]


def impute_numeric(ctx: RepairContext, row: int, col: str, issues: list[Issue]) -> Outcome:
    g = _best_grouping(ctx, col)
    if g is None:
        return refuse("impute", "group_median", f"no column groups {col} tightly enough to estimate it")
    label = ctx.trusted(row, g)
    if label is None:
        return refuse("impute", "group_median", f"{g} is unknown for this row, so no comparable group")
    vals = _numeric(ctx, col)
    members = vals[ctx.df[g].loc[vals.index] == ctx.df.at[row, g]]
    n = len(members)
    if n < MIN_GROUP:
        return refuse("impute", "group_median", f"group too small: only {n} other rows with {g} = '{label}'",
                      group=label, group_size=n)
    iqr = members.quantile(0.75) - members.quantile(0.25)
    if iqr > MAX_IQR:
        return refuse("impute", "group_median", f"ages of {g} = '{label}' vary too much (IQR {iqr:.0f})")
    med = members.median()
    value = str(int(round(med)))
    return Outcome("impute", "group_median", {value: [signal(
        "group_statistic", 1 - 0.15 * iqr / MAX_IQR,
        f"median {col} of {n} rows with {g} = '{label}' is {value} (middle half: "
        f"{members.quantile(0.25):.0f}–{members.quantile(0.75):.0f}); this is an ESTIMATE")]},
        cap_key="impute", meta={"estimate": True, "group_by": g, "group": label, "group_size": n})
