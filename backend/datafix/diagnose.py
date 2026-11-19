"""Root-cause diagnosis (docs/05_ENGINE_SPEC.md §6): where errors come from, and what mechanism made them."""
from collections import Counter, defaultdict
from itertools import combinations

import pandas as pd

from . import validators as v
from .coltypes import header_tokens
from .scan import ScanResult

PROVENANCE_HINTS = {"source", "batch", "channel", "import", "file", "system", "branch", "origin", "upload", "vendor",
                    "partner", "region", "app", "device", "agent", "operator"}
ERROR_TYPES = {"missing", "disguised_missing", "invalid_format", "inconsistent", "fd_violation", "crossfield"}
MIN_ISSUES = 10
MIN_SHARE = 0.5
MIN_LIFT = 3.0

LABELS = {
    ("missing", None): "blank {col} values",
    ("disguised_missing", None): "placeholder {col} values",
    ("invalid_format", "excel_scientific_notation"): "{col} values in scientific notation",
    ("invalid_format", "too_short"): "truncated {col} values",
    ("invalid_format", "encoding"): "garbled {col} values",
    ("invalid_format", None): "invalid {col} values",
    ("inconsistent", "date_format"): "{col} values in a different date format",
    ("inconsistent", "money_format"): "{col} values in lakh/crore or comma notation",
    ("inconsistent", "spelling"): "misspelled {col} values",
    ("inconsistent", "alias"): "old/alternate {col} names",
    ("inconsistent", None): "inconsistently written {col} values",
    ("fd_violation", None): "{col} values contradicting learned rules",
    ("crossfield", None): "{col} values failing a cross-field rule",
}
FIXES = {
    "missing": "Make {col} a required field in the {group} pipeline; recover existing blanks from learned rules or linked records.",
    "disguised_missing": "Stop the {group} form from accepting placeholders like 9999999999; treat them as blank.",
    "invalid_format": "Add format validation for {col} at the {group} entry point.",
    "inconsistent": "Standardise {col} at the {group} source (fixed format / picklist).",
    "fd_violation": "Derive {col} from related fields (e.g. PIN) instead of free entry at {group}.",
    "crossfield": "Compute {col} automatically instead of entering it.",
}

# which (issue type, kind) a pattern covers, to attach the matching source cause
PATTERN_ISSUES = {
    "placeholder": {("disguised_missing", None)},
    "truncation": {("invalid_format", "too_short"), ("invalid_format", "wrong_length")},
    "excel_scientific_notation": {("invalid_format", "excel_scientific_notation")},
    "encoding": {("invalid_format", "encoding")},
    "date_format": {("inconsistent", "date_format")},
    "money_format": {("inconsistent", "money_format")},
    "whitespace": {("inconsistent", "whitespace")},
    "case": {("inconsistent", "case")},
}

PATTERNS = {
    "excel_scientific_notation": ("Excel scientific notation",
                                  "Numbers were opened and saved in Excel, which stores long numbers as 9.87654E+09 and "
                                  "drops digits.", "Export with the column formatted as Text, or import CSVs as text."),
    "encoding": ("Encoding damage", "UTF-8 text was read as Latin-1/Windows-1252, turning ’ into â€™.",
                 "Read and write the file as UTF-8 end to end."),
    "date_format": ("Date format mix-up", "Some records use month-first (MM/DD) dates while the column is day-first.",
                    "Fix the date format at the source system; ambiguous dates from it (day ≤ 12) need review."),
    "money_format": ("Indian number notation", "Amounts typed as ₹1.2L / 1.5 Cr / 12,00,000 instead of plain numbers.",
                     "Use a numeric field with a fixed unit (rupees)."),
    "whitespace": ("Untrimmed manual entry", "Values have leading/trailing or doubled spaces.",
                   "Trim input on save."),
    "case": ("Caps-lock entry", "Some values are typed in ALL CAPS.", "Normalise case on save."),
    "placeholder": ("Placeholder values", "A required field made people type dummy values (9999999999, test@test.com).",
                    "Allow 'unknown' explicitly instead of forcing a value."),
    "truncation": ("Truncated values", "Values are shorter than they should be (5-digit PIN/phone): digits were cut "
                                       "off or mistyped.", "Validate length at entry."),
}


def _context_columns(df: pd.DataFrame, scan: ScanResult) -> list[str]:
    hinted, other = [], []
    for c, i in scan.columns.items():
        if i.semantic_type != "category" or not 2 <= i.distinct <= 30:
            continue
        (hinted if set(header_tokens(c)) & PROVENANCE_HINTS else other).append(c)
    # real provenance columns beat arbitrary categories (gender, occupation) that only add noise
    return hinted[:6] if hinted else other[:6]


def _month_column(df: pd.DataFrame, scan: ScanResult) -> pd.Series | None:
    """created_at-like date bucketed by month, as another provenance signal."""
    for c, i in scan.columns.items():
        toks = set(header_tokens(c))
        if i.semantic_type == "date" and toks & {"created", "imported", "uploaded", "loaded", "inserted", "at"}:
            return df[c].map(lambda x: (d.strftime("%Y-%m") if (d := v.parse_date(x)) else ""))
    return None


def _pct(x: float) -> str:
    if x == 0:
        return "0%"
    return f"{x:.0%}" if x >= 0.095 else f"{x:.1%}" if x >= 0.001 else f"{x:.2%}"


def _label(t: str, kind: str | None, col: str) -> str:
    tpl = LABELS.get((t, kind)) or LABELS.get((t, None)) or "{col} problems"
    return tpl.format(col=col)


def diagnose(df: pd.DataFrame, scan: ScanResult) -> list[dict]:
    causes: list[dict] = []
    ctx_cols = _context_columns(df, scan)
    contexts = {c: df[c].str.strip() for c in ctx_cols}
    month = _month_column(df, scan)
    if month is not None:
        contexts["month"] = month
    n = len(df)

    groups: dict[tuple, list[int]] = defaultdict(list)
    for i in scan.issues:
        if i.type in ERROR_TYPES and i.row_id is not None and i.column:
            kind = i.meta.get("kind") if i.type in ("invalid_format", "inconsistent") else None
            groups[(i.type, i.column, kind)].append(i.row_id)

    # ---- 1. source lift
    keys = list(contexts)
    pairs = [(a, b) for a, b in combinations(keys, 2)][:15]
    for (t, col, kind), rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        rows = sorted(set(rows))
        if len(rows) < MIN_ISSUES:
            continue
        overall = len(rows) / n
        best_single = best_pair = None
        candidates = [((k,), contexts[k]) for k in keys] + \
                     [((a, b), contexts[a] + " · " + contexts[b]) for a, b in pairs]
        for names, series in candidates:
            in_issue = series.loc[rows].value_counts()
            sizes = series.value_counts()
            for val, hits in in_issue.items():
                if not val or val.endswith(" · ") or val.startswith(" · "):
                    continue
                share = hits / len(rows)
                rate = hits / sizes[val]
                lift = rate / overall
                if share >= MIN_SHARE and lift >= MIN_LIFT:
                    entry = ((share, lift), names, val, int(hits), share, rate, lift, series, sizes)
                    if len(names) == 1 and (best_single is None or entry[0] > best_single[0]):
                        best_single = entry
                    if len(names) == 2 and (best_pair is None or entry[0] > best_pair[0]):
                        best_pair = entry
        # a pair (source + batch) wins only if it explains nearly as many issues and is far more concentrated;
        # otherwise noise columns pair up by chance
        best = best_single
        if best_pair and (best_single is None or (best_pair[4] >= 0.9 * best_single[4]
                                                  and best_pair[6] >= 2 * best_single[6])):
            best = best_pair
        if best is None:
            continue
        _, names, val, hits, share, rate, lift, series, sizes = best
        group_desc = " and ".join(f"{nm} = {vv}" for nm, vv in zip(names, val.split(" · ")))
        label = _label(t, kind, col)
        others = (len(rows) - hits) / max(n - sizes[val], 1)
        by_group = [{"value": g, "rows": int(sizes[g]), "issues": int(series.loc[rows].value_counts().get(g, 0)),
                     "rate": round(float(series.loc[rows].value_counts().get(g, 0) / sizes[g]), 4)}
                    for g in sizes.index[:12] if g]
        causes.append({
            "cause_id": "", "kind": "source_lift", "issue_type": t, "column": col, "issue_kind": kind,
            "title": f"{hits} of {len(rows)} {label} come from {group_desc}",
            "group": {"columns": list(names), "value": val},
            "share_of_issues": round(share, 4), "lift": round(lift, 1), "issue_count": len(rows),
            "explanation": f"{_pct(rate)} of rows from {group_desc} have {label}, "
                           + (f"against {_pct(others)} elsewhere ({rate / others:.0f}× more likely)" if others
                              else "and no rows from anywhere else do")
                           + ". The problem is in that pipeline, not random typing.",
            "suggested_fix": FIXES.get(t, "Fix {col} at {group}.").format(col=col, group=group_desc),
            "rate_by_group": by_group,
        })

    # ---- 2. pattern causes (mechanisms)
    pattern_hits: dict[str, Counter] = defaultdict(Counter)
    for i in scan.issues:
        kind = i.meta.get("kind")
        if i.type == "disguised_missing":
            pattern_hits["placeholder"][i.column] += 1
        elif kind in ("too_short", "wrong_length"):
            pattern_hits["truncation"][i.column] += 1
        elif kind in PATTERNS:
            pattern_hits[kind][i.column] += 1
    lift_causes = list(causes)
    for key, cols in sorted(pattern_hits.items(), key=lambda kv: -sum(kv[1].values())):
        title, why, fix = PATTERNS[key]
        total = sum(cols.values())
        where = next((c for c in lift_causes if c["column"] in cols
                      and (c["issue_type"], c["issue_kind"]) in PATTERN_ISSUES[key]), None)
        causes.append({
            "cause_id": "", "kind": "pattern", "issue_type": key, "issue_kind": key, "column": ", ".join(cols),
            "title": f"{title}: {total} values in {', '.join(f'{c} ({n})' for c, n in cols.most_common())}",
            "group": where["group"] if where else None, "share_of_issues": None, "lift": None,
            "issue_count": total,
            "explanation": why + (f" Concentrated in {where['title'].split(' come from ')[-1]}." if where else ""),
            "suggested_fix": fix, "rate_by_group": [],
        })
    for k, c in enumerate(causes, 1):
        c["cause_id"] = f"RC{k:02d}"
    return causes
