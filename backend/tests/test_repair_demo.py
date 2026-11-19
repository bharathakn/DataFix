"""Phase 2A exit test: repair proposals on the demo data vs truth.json."""
import json
from collections import Counter
from pathlib import Path

import pytest

from datafix import validators as v
from datafix.planner import plan_tables, preview_apply

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo"
pytestmark = pytest.mark.skipif(not (DEMO / "truth.json").exists(), reason="run scripts/make_demo_data.py")


@pytest.fixture(scope="module")
def planned():
    tables, scans, props, timings = plan_tables({"customers": str(DEMO / "customers_dirty.csv"),
                                                 "orders": str(DEMO / "orders.csv")})
    truth = json.loads((DEMO / "truth.json").read_text())
    return tables, scans, props, timings, truth


def _equal(col: str, a: str, b: str) -> bool:
    if col == "phone":
        return v.normalize_phone(a) == v.normalize_phone(b)
    if col == "email":
        return a.strip().casefold() == b.strip().casefold()
    return a.strip() == b.strip()


def evaluate(tables, props, truth, tiers):
    df = tables["customers"]
    truth_cells = {(t["dirty_row"], t["column"]): t for t in truth["customers_cell_errors"]}
    dup_ids = {d["customer_id"] for d in truth["customers_duplicates"]}
    dup_of = {d["customer_id"]: d["duplicate_of"] for d in truth["customers_duplicates"]}
    row_of = dict(zip(df["customer_id"], df.index))
    applied = [p for p in props if p.table == "customers" and p.tier in tiers and p.candidates]
    correct, wrong, estimates, false_repairs = Counter(), Counter(), 0, []
    for p in applied:
        if p.column == "__row__":
            ok = df.at[p.row_id, "customer_id"] in dup_ids
            (correct if ok else wrong)["duplicate"] += 1
            continue
        t = truth_cells.get((p.row_id, p.column))
        if t is None:
            # a near-duplicate made by re-formatting the source's e-mail/phone: writing it back in the source's
            # form is a correct normalisation, not a false repair
            src = row_of.get(dup_of.get(df.at[p.row_id, "customer_id"], ""))
            if src is not None and p.candidates[0].value == df.at[src, p.column]:
                continue
            false_repairs.append((p.row_id, p.column, p.original_value, p.candidates[0].value))
            continue
        if p.repair_class == "impute":
            estimates += 1
            continue
        if _equal(p.column, p.candidates[0].value, t["clean_value"]):
            correct[t["error_type"]] += 1
        else:
            wrong[t["error_type"]] += 1
            print("WRONG", t["error_type"], p.row_id, p.column, repr(p.original_value), "->",
                  repr(p.candidates[0].value), "truth", repr(t["clean_value"]))
    n_ok, n_bad = sum(correct.values()), sum(wrong.values())
    errors_total = len(truth_cells) + len(dup_ids)
    return {"precision": n_ok / max(n_ok + n_bad, 1), "correct": n_ok, "wrong": n_bad, "estimates": estimates,
            "coverage": (n_ok + n_bad + estimates) / errors_total, "false_repairs": false_repairs,
            "wrong_by_type": dict(wrong)}


def test_auto_tier_is_safe(planned):
    tables, _, props, timings, truth = planned
    ev = evaluate(tables, props, truth, ("auto",))
    print(f"\n{timings} | auto: precision {ev['precision']:.4f}, {ev['correct']} correct, {ev['wrong']} wrong, "
          f"coverage {ev['coverage']:.3f}, false repairs {len(ev['false_repairs'])}")
    assert ev["precision"] >= 0.99
    assert not ev["false_repairs"]


def test_auto_plus_review(planned):
    tables, _, props, _, truth = planned
    ev = evaluate(tables, props, truth, ("auto", "review"))
    print(f"\nauto+review: precision {ev['precision']:.4f}, {ev['correct']} correct, {ev['wrong']} wrong, "
          f"{ev['estimates']} estimates, coverage {ev['coverage']:.3f}")
    assert ev["precision"] >= 0.95
    assert not ev["false_repairs"]


def test_story_rows(planned):
    _, _, props, _, _ = planned
    by = {(p.table, p.row_id, p.column): p for p in props}
    p412 = by[("customers", 412, "pin")]
    assert p412.candidates[0].value == "400001" and p412.tier == "auto"
    assert by[("customers", 52, "city")].candidates[0].value == "Bengaluru"
    p777 = by[("customers", 777, "phone")]
    assert p777.tier == "auto" and p777.candidates[0].value.startswith("80281")
    p1043 = by[("customers", 1043, "phone")]
    assert p1043.tier == "refused" and "won't guess" in p1043.refusal_reason
    assert by[("customers", 2001, "age")].tier == "review"
    p2002 = by[("customers", 2002, "age")]
    assert p2002.tier == "refused" and "too small" in p2002.refusal_reason
    p3000 = by[("customers", 3000, "annual_income")]
    assert p3000.tier == "flag" and not p3000.candidates


def test_duplicates_remap_orders(planned):
    tables, _, props, _, _ = planned
    merges = [p for p in props if p.column == "__row__" and p.meta["fk_remaps"]]
    assert merges, "near duplicates with orders should re-point those orders"
    out = preview_apply(tables, props, ("auto", "review"))
    ids = set(out["customers"]["customer_id"])
    assert set(out["orders"]["customer_id"]) <= ids  # no orphaned orders


def test_clean_file_gets_no_repairs():
    _, _, props, _ = plan_tables({"customers": str(DEMO / "customers_clean.csv")})
    acting = [p for p in props if p.tier in ("auto", "review")]
    assert not acting, Counter((p.column, p.algorithm) for p in acting)
