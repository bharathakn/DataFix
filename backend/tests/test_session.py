"""Phase 2B: change log, checkpoints, undo / redo / restore, hash chain, persistence."""
import copy
from pathlib import Path

import pandas as pd
import pytest

from datafix.session import ROW, Session

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo"
pytestmark = pytest.mark.skipif(not (DEMO / "truth.json").exists(), reason="run scripts/make_demo_data.py")


@pytest.fixture(scope="module")
def base():
    return Session.from_paths({"customers": str(DEMO / "customers_dirty.csv"), "orders": str(DEMO / "orders.csv")})


@pytest.fixture
def s(base):
    return copy.deepcopy(base)


@pytest.fixture
def fixed(s):
    s.apply_auto()
    return s


def _diff_cells(a: pd.DataFrame, b: pd.DataFrame) -> int:
    common = a.index.intersection(b.index)
    return int((a.loc[common] != b.loc[common]).sum().sum())


def test_original_is_never_mutated(fixed):
    orig = pd.read_csv(DEMO / "customers_dirty.csv", dtype=str, keep_default_na=False)
    assert fixed.originals["customers"].equals(orig)
    assert _diff_cells(fixed.current(), fixed.originals["customers"]) > 1000


def test_auto_batches_and_scores(fixed):
    labels = [k.label for k in fixed.checkpoints]
    assert labels[0] == "Original" and "Duplicates merged" in labels and "PIN / address recovered" in labels
    scores = [k.quality_score for k in fixed.checkpoints]
    assert scores == sorted(scores) and scores[-1] > scores[0]
    applied = {p.proposal_id for p in fixed.proposals.values() if p.status == "applied"}
    assert applied == {p.proposal_id for p in fixed.proposals.values() if p.tier == "auto"}


def test_story_412_applied_and_logged(fixed):
    assert fixed.current().at[412, "pin"] == "400001"
    c = next(c for c in fixed.changes if c.row_id == 412 and c.column == "pin")
    assert c.original_value == "40001" and c.new_value == "400001" and c.confidence >= 0.95
    assert "india_post_directory" in c.source and any("Stock Exchange" in e for e in c.evidence)


def test_replay_matches_incremental_cache(fixed):
    incremental = fixed.current().copy()
    fixed._cache = {}
    assert fixed.current().equals(incremental)


def test_undo_cell_batch_and_restore(fixed):
    k_pin = next(k for k in fixed.checkpoints if k.label == "PIN / address recovered")
    c412 = next(c for c in fixed.changes if c.row_id == 412 and c.column == "pin")
    fixed.undo_change(c412.change_id)
    assert fixed.current().at[412, "pin"] == "40001"
    fixed.undo_checkpoint(k_pin.checkpoint_id)
    assert all(fixed._by_id(cid).status == "undone" for cid in k_pin.change_ids)
    fixed.restore("K00")
    assert fixed.current().equals(fixed.originals["customers"])
    last = fixed.checkpoints[-1].checkpoint_id
    fixed.restore(last)  # forward again
    assert fixed.current().at[412, "pin"] == "400001"
    assert fixed.verify_audit()["valid"]


def test_merge_removes_row_remaps_orders_and_undoes_atomically(fixed):
    merge = next(p for p in fixed.proposals.values() if p.column == ROW and p.meta["fk_remaps"])
    fixed.review(merge.proposal_id, "accept")
    cust, orders = fixed.current("customers"), fixed.current("orders")
    assert merge.row_id not in cust.index
    assert set(orders["customer_id"]) <= set(cust["customer_id"])
    fixed.undo_change(merge.meta["change_ids"][0])
    assert merge.row_id in fixed.current("customers").index
    remap = merge.meta["fk_remaps"][0]
    assert fixed.current("orders").at[remap["row_id"], "customer_id"] == remap["old"]


def test_review_actions(fixed):
    pending = [p for p in fixed.proposals.values() if p.tier == "review" and p.status == "pending"
               and p.column != ROW and len(p.candidates) >= 1]
    a, b, c = pending[:3]
    fixed.review(a.proposal_id, "accept")
    assert fixed.current(a.table).at[a.row_id, a.column] == a.candidates[0].value
    fixed.review(b.proposal_id, "reject")
    assert b.status == "rejected" and fixed.current(b.table).at[b.row_id, b.column] == b.original_value
    fixed.review(c.proposal_id, "choose", custom_value="CUSTOM")
    assert fixed.current(c.table).at[c.row_id, c.column] == "CUSTOM"
    assert fixed.checkpoints[-1].kind == "review" and fixed.verify_audit()["valid"]


def test_tampering_is_detected(fixed):
    assert fixed.verify_audit()["valid"]
    victim = fixed.changes[100]
    victim.new_value = "tampered"
    res = fixed.verify_audit()
    assert not res["valid"] and res["broken_at"] == victim.change_id


def test_status_column_and_change_log(fixed):
    out = fixed.cleaned()
    assert list(out.columns)[:-1] == list(fixed.originals["customers"].columns)
    st = out["_datafix_status"]
    assert st[412] == "repaired" and st[1043] == "needs_review" and st[3000] == "needs_review"
    assert st.value_counts()["unchanged"] > 7000
    log = fixed.change_log()
    assert len(log) == len(fixed.changes) and log["hash"].is_unique
    assert log.loc[log["row_id"] == 412, "record_id"].iloc[0] == "C-10413"


def test_clean_cells_never_changed(fixed):
    flagged = {(i.row_id, i.column) for i in fixed.scans["customers"].issues if i.row_id is not None}
    dup_rows = {i.row_id for i in fixed.scans["customers"].issues if i.column is None and i.row_id is not None}
    for c in fixed.applied_changes("customers"):
        if c.column == ROW:
            assert c.row_id in dup_rows
        elif not c.reason.startswith("filled from duplicate"):
            assert (c.row_id, c.column) in flagged, c


def test_save_and_load(fixed, tmp_path):
    path = fixed.save(tmp_path)
    again = Session.load(path)
    assert again.current().equals(fixed.current()) and again.verify_audit()["valid"]
