"""Groq backup provider: mocked HTTP only, never a live call."""
import json

import httpx
import pytest

from datafix import llm as L


class FakeResp:
    def __init__(self, status: int, body: dict | None = None, headers: dict | None = None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"{self.status_code}", request=httpx.Request("POST", L.GROQ_URL),
                                        response=httpx.Response(self.status_code))

    def json(self):
        return self._body


@pytest.fixture
def env(monkeypatch):
    for k in ("GEMINI_API_KEY", "GEMINI_API_KEY_BACKUP", "DATAFIX_OFFLINE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_secret")
    L.reset_llm()
    yield monkeypatch
    L.reset_llm()


def _post_returning(sent: list, *responses):
    it = iter(responses)

    def fake_post(url, json=None, timeout=None, headers=None):
        sent.append({"url": url, "json": json, "headers": headers})
        return next(it)
    return fake_post


def test_groq_used_when_no_gemini_key_and_payload_is_sanitized(env):
    sent: list = []
    env.setattr(httpx, "post", _post_returning(sent, FakeResp(200, {"choices": [{"message": {"content": "Fine."}}]})))
    llm = L.get_llm()
    assert llm.enabled and not llm.gemini_enabled
    text, mode = L.causes_narrative([{"title": "Mumbai PINs", "explanation": "call 9876543210 or a@b.com"}])
    assert (text, mode) == ("Fine.", "groq")
    body = json.dumps(sent[0]["json"])
    assert "9876543210" not in body and "a@b.com" not in body
    assert sent[0]["headers"]["Authorization"] == "Bearer gsk_test_secret"
    st = llm.status()
    assert st["provider"] == "groq" and st["model"] == L.GROQ_DEFAULT_MODEL and st["backup"]["configured"]
    assert "gsk_test_secret" not in json.dumps(st)


def test_groq_429_cools_down_and_falls_back_to_template(env):
    sent: list = []
    env.setattr(httpx, "post", _post_returning(sent, FakeResp(429, headers={"retry-after": "30"})))
    _, mode = L.causes_narrative([{"title": "A", "explanation": "b"}])
    assert mode == "offline" and len(sent) == 1
    _, mode = L.causes_narrative([{"title": "C", "explanation": "d"}])
    assert mode == "offline" and len(sent) == 1  # cooling down: no second request
    st = L.get_llm().status()
    assert st["backup"]["cooling_down"] > 0 and "gsk_test_secret" not in json.dumps(st)


def test_gemini_failure_falls_through_to_groq(env):
    env.setenv("GEMINI_API_KEY", "fake")
    llm = L.get_llm()

    def boom(*a, **k):
        raise L.LLMUnavailable("429 RESOURCE_EXHAUSTED")
    env.setattr(llm, "generate", boom)
    env.setattr(httpx, "post", _post_returning([], FakeResp(200, {"choices": [{"message": {"content": "via groq"}}]})))
    assert llm.text("hello") == "via groq" and llm.last_provider == "groq"
    assert llm.status()["provider"] == "groq"


def test_offline_flag_disables_groq(env):
    env.setenv("DATAFIX_OFFLINE", "1")
    assert not L.get_llm().enabled
    assert L.get_llm().status()["provider"] == "offline"


def test_groq_chat_runs_only_whitelisted_tools(env):
    from pathlib import Path
    from datafix.chat_tools import answer
    from datafix.session import Session
    root = Path(__file__).resolve().parents[2]
    s = Session.from_paths({"customers": str(root / "data/demo/customers_dirty.csv")})
    s.plan()
    call = lambda name, args: {"id": "t1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    sent: list = []
    env.setattr(httpx, "post", _post_returning(
        sent,
        FakeResp(200, {"choices": [{"message": {"content": None, "tool_calls": [
            call("count_rows", {"filters": [{"column": "city", "op": "eq", "value": "Bengaluru"}]}),
            call("eval", {"code": "__import__('os')"})]}}]}),
        FakeResp(200, {"choices": [{"message": {"content": "There are many rows."}}]})))
    r = answer(s, "How many rows are from Bengaluru?")
    assert r["mode"] == "groq" and r["text"] == "There are many rows."
    assert [c["name"] for c in r["tool_calls"]] == ["count_rows", "eval"]
    assert r["tool_calls"][0]["result_preview"]["count"] > 1000
    assert "unknown tool" in r["tool_calls"][1]["result_preview"]["error"]
    assert sent[0]["json"]["tools"][0]["type"] == "function"
