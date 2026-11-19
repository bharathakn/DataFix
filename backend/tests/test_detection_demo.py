"""Phase 1 exit test: detection on the seeded demo data vs truth.json."""
import json
from collections import Counter
from pathlib import Path

import pytest

from datafix.ingest import load_path
from datafix.scan import scan_table

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo"
pytestmark = pytest.mark.skipif(not (DEMO / "truth.json").exists(), reason="run scripts/make_demo_data.py")

# Errors a single cell cannot reveal: a US date with day <= 12 is a valid DD/MM date.
MIN_RECALL = {"date_format": 0.5}
NOT_ERRORS = {"anomaly", "sparse_column"}


@pytest.fixture(scope="module")
def dirty():
    df = load_path(DEMO / "customers_dirty.csv").df
    return df, scan_table(df, "customers_dirty.csv"), json.loads((DEMO / "truth.json").read_text())


def evaluate(df, res, truth):
    row_of = {cid: i for i, cid in enumerate(df["customer_id"])}
    true_cells = {(t["dirty_row"], t["column"]): t["error_type"] for t in truth["customers_cell_errors"]}
    true_dups = {row_of[d["customer_id"]]: d["error_type"] for d in truth["customers_duplicates"]}
    flagged = {(i.row_id, i.column) for i in res.issues if i.column and i.row_id is not None
               and i.type not in NOT_ERRORS}
    flagged_dups = {i.row_id for i in res.issues if i.type in ("duplicate", "near_duplicate")}
    hit, total = Counter(), Counter()
    for cell, et in true_cells.items():
        total[et] += 1
        hit[et] += cell in flagged
    for r, et in true_dups.items():
        total[et] += 1
        hit[et] += r in flagged_dups
    tp = sum(hit.values())
    n_flags = len(flagged) + len(flagged_dups)
    false_cells = sorted(flagged - set(true_cells))
    return {
        "recall_by_type": {et: hit[et] / total[et] for et in total},
        "precision": tp / n_flags,
        "recall": tp / sum(total.values()),
        "false_cells": false_cells,
        "false_dups": sorted(flagged_dups - set(true_dups)),
    }


def test_detection_quality(dirty):
    df, res, truth = dirty
    ev = evaluate(df, res, truth)
    print("\nrecall by type:", {k: round(v, 3) for k, v in sorted(ev["recall_by_type"].items())})
    print(f"precision {ev['precision']:.3f}  recall {ev['recall']:.3f}  false cells {len(ev['false_cells'])}")
    for et, r in ev["recall_by_type"].items():
        assert r >= MIN_RECALL.get(et, 0.9), (et, r)
    assert ev["precision"] >= 0.95
    assert ev["recall"] >= 0.9
    assert not ev["false_dups"]


def test_story_rows_flagged(dirty):
    df, res, _ = dirty
    cells = {(i.row_id, i.column): i for i in res.issues if i.column}
    assert cells[(412, "pin")].type == "invalid_format"
    assert cells[(52, "city")].meta["kind"] == "spelling"
    assert cells[(777, "phone")].meta["kind"] == "too_short"
    assert cells[(1043, "phone")].type == "missing"
    assert cells[(3000, "annual_income")].type == "anomaly"


def test_learned_rules(dirty):
    _, res, _ = dirty
    rules = {(r.lhs, r.rhs) for r in res.rules}
    assert ("pin", "city") in rules and ("city", "state") in rules


def test_clean_file_has_no_false_errors():
    df = load_path(DEMO / "customers_clean.csv").df
    res = scan_table(df, "customers_clean.csv")
    errors = [i for i in res.issues if i.type not in NOT_ERRORS]
    print(f"\nclean file: {len(errors)} error flags, score {res.quality_score}")
    assert len(errors) <= 0.001 * len(df) * len(df.columns), Counter(i.type for i in errors)


def test_renamed_pin_column_detected():
    df = load_path(DEMO / "customers_dirty.csv").df.rename(columns={"pin": "col_7"})
    from datafix.coltypes import infer_columns
    from datafix.reference import pin_reference
    assert infer_columns(df[["col_7"]], pin_reference())["col_7"].semantic_type == "pin"
