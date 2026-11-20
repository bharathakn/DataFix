"""External answer key: data/testsets/df55 (55 customer rows + the expected action per row).

Scored by behaviour, not by values written into the engine:
- "No repair expected"        -> the row gets no issue and no proposal
- needs_human_review = Yes    -> the row has a problem, and nothing on it is applied automatically
                                 (review / flag / refused only)
- needs_human_review = No     -> at least one fix on the row is in the auto tier, except a date whose
                                 day and month are both <= 12: the key only asks for conversion "if parsing is
                                 unambiguous", so offering both readings for review is the expected behaviour
"""
from pathlib import Path

import pandas as pd
import pytest

from datafix.ingest import load_path
from datafix.planner import plan_repairs
from datafix.scan import scan_table

DIR = Path(__file__).resolve().parents[2] / "data" / "testsets" / "df55"


@pytest.fixture(scope="module")
def result():
    df = load_path(str(DIR / "datafix_input_dataset.csv")).df
    scan = scan_table(df, "t")
    props = plan_repairs({"t": df}, {"t": scan})
    key = pd.read_csv(DIR / "datafix_expected_results.csv", dtype=str, keep_default_na=False)
    row_of = {rid.strip(): r for r, rid in df["record_id"].items()}
    issues, by_row = {}, {}
    for i in scan.issues:
        if i.row_id is not None:
            issues.setdefault(i.row_id, []).append(i)
    for p in props:
        by_row.setdefault(p.row_id, []).append(p)
    return key, row_of, issues, by_row, scan


def _verdict(exp, row, issues, by_row) -> str | None:
    props = by_row.get(row, [])
    if exp.expected_action == "No repair expected":
        return None if not issues.get(row) and not props else f"unexpected {[(p.column, p.tier) for p in props]}"
    if not props:
        return "problem not detected"
    if exp.needs_human_review == "Yes":
        auto = [p.column for p in props if p.tier == "auto"]
        return f"applied without review: {auto}" if auto else None
    if any(p.tier == "auto" for p in props):
        return None
    ambiguous_date = any(p.algorithm == "date_reformat" and len(p.candidates) > 1 for p in props)
    return None if ambiguous_date else f"not auto: {[(p.column, p.tier) for p in props]}"


def test_every_row_matches_the_answer_key(result):
    key, row_of, issues, by_row, _ = result
    wrong = {}
    for exp in key.itertuples():
        msg = _verdict(exp, row_of[exp.test_case_id], issues, by_row)
        if msg:
            wrong[exp.test_case_id] = msg
    assert not wrong, wrong


def test_column_types(result):
    *_, scan = result
    types = {c: i.semantic_type for c, i in scan.columns.items()}
    assert types["age"] == "age" and types["customer_status"] == "category"
    assert types["customer_name"] == "name" and types["purchase_amount"] == "money"


@pytest.mark.parametrize("rid,col,value", [
    ("DF018", "signup_date", "2025-07-03"), ("DF019", "city", "Bengaluru"), ("DF020", "city", "Mumbai"),
    ("DF020", "customer_status", "Active"), ("DF025", "customer_status", "Active"),
    ("DF035", "city", "Delhi"), ("DF036", "city", "Kolkata"), ("DF037", "city", "Chennai"),
    ("DF038", "customer_name", "Kavya Rao"), ("DF040", "customer_status", "Active"),
    ("DF041", "customer_status", "Active"), ("DF054", "purchase_amount", "1850"),
    # review suggestions
    ("DF015", "email", "priya.shah@example.com"), ("DF024", "customer_status", "Active"),
    ("DF042", "customer_status", "Active"),
])
def test_suggested_values(result, rid, col, value):
    _, row_of, _, by_row, _ = result
    p = next(p for p in by_row[row_of[rid]] if p.column == col)
    assert p.candidates and p.candidates[0].value == value


def test_outlier_flagged_not_changed(result):
    _, row_of, _, by_row, _ = result
    (p,) = by_row[row_of["DF023"]]
    assert p.tier == "flag" and not p.candidates
