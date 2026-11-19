"""Phase 3: do-no-harm validation, benchmark, root cause, privacy, export, quality gate."""
import copy
import json
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

from datafix.__main__ import main as cli
from datafix.export import export_bundle
from datafix.privacy import find_spans, mask_value
from datafix.session import Session

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo"
pytestmark = pytest.mark.skipif(not (DEMO / "truth.json").exists(), reason="run scripts/make_demo_data.py")


@pytest.fixture(scope="module")
def fixed_base():
    s = Session.from_paths({"customers": str(DEMO / "customers_dirty.csv"), "orders": str(DEMO / "orders.csv")})
    s.apply_auto()
    return s


@pytest.fixture
def fixed(fixed_base):
    return copy.deepcopy(fixed_base)


def test_do_no_harm_all_pass(fixed):
    v = fixed.validate()
    failed = [c for c in v["checks"] if not c["passed"]]
    assert not failed, failed
    assert len(v["checks"]) == 8
    assert v["dimensions_after"]["clean_rows"] > v["dimensions_before"]["clean_rows"] + 10


def test_do_no_harm_catches_a_bad_repair(fixed):
    # simulate a harmful edit to a clean cell, logged like a repair
    k = fixed._new_checkpoint("bad", "user")
    fixed._record(k, None, "customers", 5, "name", "Wrong Name", "test", [], "test", 1.0, "manual", "user")
    v = fixed.validate()
    assert not next(c for c in v["checks"] if c["name"] == "valid_cells_changed")["passed"]


def test_benchmark(fixed):
    r = fixed.run_benchmark(seed=7)
    assert r["injected"] >= 100
    assert r["detection"]["precision"] >= 0.95 and r["detection"]["recall"] >= 0.95
    assert r["repair"]["precision"] >= 0.98
    assert r["repair"]["false_repair_rate"] <= 0.005
    assert r["calibration"]


def test_root_causes(fixed):
    causes = fixed.diagnose()
    titles = [c["title"] for c in causes]
    assert any("71 of 73 blank city" in t and "B07" in t for t in titles)
    assert any("partner_api" in t and "date format" in t for t in titles)
    assert any(c["kind"] == "pattern" and "Excel" in c["title"] for c in causes)
    assert not any("gender" in t for t in titles)  # no noise columns in explanations


def test_privacy_scan_finds_planted_pii(fixed):
    found = {(f["column"], f["pii_type"]): f for f in fixed.privacy_scan() if f["table"] == "customers"}
    assert found[("notes", "aadhaar")]["rows"] == 25 and found[("notes", "aadhaar")]["validated_by"] == "Verhoeff checksum"
    assert found[("notes", "pan")]["rows"] == 15 and found[("notes", "phone")]["rows"] == 10
    assert found[("phone", "phone")]["risk"] == "medium"


def test_find_spans_and_masks():
    text = "KYC verified, Aadhaar 2345 6789 0124 and call 9876543210"
    kinds = [k for _, _, k, _ in find_spans(text)]
    assert "phone" in kinds
    assert mask_value("9876543210", "phone", "partial") == "98XXXXXX10"
    assert mask_value("rahul@gmail.com", "email", "partial") == "ra***@gmail.com"
    a = mask_value("98765 43210", "phone", "hash", "salt")
    assert a == mask_value("+91 9876543210", "phone", "hash", "salt")  # hashing keeps duplicates detectable


def test_mask_and_undo(fixed):
    k = fixed.mask_column("notes", "redact")
    cur = fixed.current()
    assert all("REDACTED" in cur.at[fixed._by_id(c).row_id, "notes"] for c in k.change_ids)
    k2 = fixed.mask_column("pan", "drop")
    assert "pan" not in fixed.current().columns
    fixed.undo_checkpoint(k2.checkpoint_id)
    assert "pan" in fixed.current().columns
    v = fixed.validate()
    assert all(c["passed"] for c in v["checks"]), [c for c in v["checks"] if not c["passed"]]


def test_export_bundle(fixed, tmp_path):
    fixed.mask_column("notes", "partial")
    files = export_bundle(fixed, tmp_path)
    names = set(zipfile.ZipFile(files["zip"]).namelist())
    for n in ("cleaned_data.csv", "cleaned_highlighted.xlsx", "quality_report.html", "change_log.csv",
              "privacy_report.csv", "cleaning_recipe.json"):
        assert f"datafix_output/{n}" in names
    html = files["quality_report.html"].read_text()
    assert "71 of 73 blank city" in html and "verified" in html
    ws = load_workbook(files["cleaned_highlighted.xlsx"])["Cleaned data"]
    hdr = [c.value for c in ws[1]]
    cell = ws[412 + 2][hdr.index("pin")]
    assert cell.value == "400001" and "40001" in cell.comment.text
    recipe = json.loads(files["cleaning_recipe.json"].read_text())
    assert recipe["steps"] and recipe["column_types"]["pin"] == "pin"


def test_quality_gate(tmp_path, capsys):
    assert cli(["check", str(DEMO / "customers_dirty.csv"), "--min", "clean_rows=95"]) == 1
    assert cli(["check", str(DEMO / "customers_clean.csv"), "--min", "clean_rows=99", "--min-score", "99"]) == 0
