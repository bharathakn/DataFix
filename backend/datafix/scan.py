"""Scan orchestration: types -> detectors -> score."""
import time
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from .coltypes import infer_columns
from .detect import ScanContext
from .detect.anomalies import detect_anomalies
from .detect.consistency import detect_consistency
from .detect.crossfield import detect_crossfield
from .detect.duplicates import detect_duplicates
from .detect.fd import detect_fd
from .detect.formats import detect_formats
from .detect.missing import detect_missing
from .models import ColumnInfo, Issue, LearnedRule
from .reference import pin_reference
from .validate import quality_score

DETECTORS = [detect_missing, detect_formats, detect_consistency, detect_fd, detect_crossfield, detect_anomalies,
             detect_duplicates]


@dataclass
class ScanResult:
    table: str
    n_rows: int
    columns: dict[str, ColumnInfo]
    issues: list[Issue]
    rules: list[LearnedRule]
    quality_score: float
    canonical: dict[str, dict[str, str]] = field(default_factory=dict)
    fd_maps: dict[str, dict] = field(default_factory=dict)
    timings_ms: dict[str, int] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(i.type for i in self.issues if i.row_id is not None))

    @property
    def by_column(self) -> dict[str, dict[str, int]]:
        out: dict[str, Counter] = {}
        for i in self.issues:
            if i.row_id is not None and i.column:
                out.setdefault(i.column, Counter())[i.type] += 1
        return {c: dict(v) for c, v in out.items()}


def scan_table(df: pd.DataFrame, table: str = "table", columns: dict[str, ColumnInfo] | None = None,
               overrides: dict[str, str] | None = None, use_reference: bool = True) -> ScanResult:
    ref = pin_reference() if use_reference else None
    timings: dict[str, int] = {}
    t0 = time.perf_counter()
    cols = columns or infer_columns(df, ref, overrides)
    timings["coltypes"] = int((time.perf_counter() - t0) * 1000)
    ctx = ScanContext(df, cols, ref)
    for det in DETECTORS:
        t = time.perf_counter()
        det(ctx)
        timings[det.__name__.removeprefix("detect_")] = int((time.perf_counter() - t) * 1000)
    for n, issue in enumerate(ctx.issues, 1):
        issue.issue_id = f"I{n:05d}"
    score = quality_score(ctx.issues, len(df), len(df.columns))
    timings["total"] = int((time.perf_counter() - t0) * 1000)
    return ScanResult(table, len(df), cols, ctx.issues, ctx.rules, score, ctx.canonical, ctx.fd_maps, timings)
