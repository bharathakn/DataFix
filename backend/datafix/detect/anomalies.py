"""Statistical outliers. Flag only: an unusual value is not automatically an error."""
import numpy as np
import pandas as pd

from .. import validators as v
from . import ScanContext

Z_LIMIT = 3.5


def detect_anomalies(ctx: ScanContext) -> None:
    for col, info in ctx.columns.items():
        if info.semantic_type not in ("number", "money", "age"):
            continue
        parse = v.parse_money if info.semantic_type == "money" else _num
        vals = ctx.df[col][ctx.usable(col)].map(parse).dropna().astype(float)
        if len(vals) < 30:
            continue
        x = vals
        logged = False
        if (vals > 0).all() and vals.skew() > 1:
            x, logged = np.log(vals), True
        med = x.median()
        mad = (x - med).abs().median()
        if mad == 0:
            continue
        z = 0.6745 * (x - med) / mad
        out = z[z.abs() > Z_LIMIT]
        for rid, score in out.items():
            ctx.add(rid, col, "anomaly", "anomaly:robust_z",
                    f"{col} {ctx.df.at[rid, col]} is unusual (robust z = {score:.1f}{', log scale' if logged else ''}); "
                    "flagged for review, not changed", ctx.df.at[rid, col], z=round(float(score), 2),
                    median=float(np.exp(med) if logged else med))


def _num(x: str) -> float | None:
    try:
        return float(x)
    except ValueError:
        return None
