"""Phase 4: every endpoint through the full demo flow (offline), plus chat-tool safety."""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not (ROOT / "data/demo/truth.json").exists(), reason="run scripts/make_demo_data.py")


def test_smoke_all_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFIX_OFFLINE", "1")
    monkeypatch.setenv("DATAFIX_SESSION_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "scripts" / "smoke_api.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    timings = smoke.run(live=False, verbose=False)
    assert len(timings) >= 40


@pytest.fixture(scope="module")
def tools():
    from datafix.chat_tools import ChatTools
    from datafix.session import Session
    s = Session.from_paths({"customers": str(ROOT / "data/demo/customers_dirty.csv")})
    s.apply_auto()
    return ChatTools(s)


def test_chat_tools_validate_arguments(tools):
    from datafix.chat_tools import ToolError
    with pytest.raises(ToolError):
        tools.run("count_rows", {"filters": [{"column": "nope", "op": "eq", "value": "x"}]})
    with pytest.raises(ToolError):
        tools.run("count_rows", {"filters": [{"column": "city", "op": "__import__('os')", "value": "x"}]})
    with pytest.raises(ToolError):
        tools.run("eval", {})
    # a "value" that looks like code is just a string compared against cells
    assert tools.run("count_rows", {"filters": [{"column": "city", "op": "eq", "value": "__import__('os').system('x')"}]})["count"] == 0


def test_chat_tools_mask_pii_and_alias(tools):
    rows = tools.run("list_rows", {"columns": ["name", "phone", "email"], "limit": 3})["rows"]
    assert all("XXXXXX" in r[2] and "***@" in r[3] for r in rows if r[2] and r[3])
    a = tools.run("count_rows", {"filters": [{"column": "city", "op": "eq", "value": "Bangalore"}]})["count"]
    b = tools.run("count_rows", {"filters": [{"column": "city", "op": "eq", "value": "Bengaluru"}]})["count"]
    assert a == b > 1000  # alias-aware equality


def test_offline_answers(tools, monkeypatch):
    monkeypatch.setenv("DATAFIX_OFFLINE", "1")
    from datafix.chat_tools import answer
    from datafix.llm import reset_llm
    reset_llm()
    r = answer(tools.s, "Why did row 412 change?")
    assert r["mode"] == "offline" and "400001" in r["text"]
    r = answer(tools.s, "Undo the city fixes")
    assert r["proposed_action"]["kind"] == "undo_changes"


def test_sanitize_masks_pii():
    from datafix.llm import sanitize
    out = sanitize({"q": "call 9876543210 or mail rahul@gmail.com", "n": 5})
    assert "9876543210" not in out["q"] and "rahul@" not in out["q"] and out["n"] == 5
