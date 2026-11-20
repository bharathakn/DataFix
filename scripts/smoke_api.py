"""Smoke test: drive every API endpoint in-process through the full demo flow.

cd backend && uv run python ../scripts/smoke_api.py            # offline (no Gemini)
cd backend && uv run python ../scripts/smoke_api.py --live     # also exercise Gemini chat/narratives
"""
import io
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(live: bool = False, verbose: bool = True) -> dict:
    if not live:
        os.environ["DATAFIX_OFFLINE"] = "1"
    os.environ.setdefault("DATAFIX_SESSION_DIR", tempfile.mkdtemp(prefix="datafix_smoke_"))
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient

    from api.main import app
    from datafix.llm import reset_llm
    reset_llm()
    c = TestClient(app)
    timings: dict[str, int] = {}

    def call(method: str, path: str, expect: int = 200, **kw):
        t = time.perf_counter()
        r = getattr(c, method)(f"/api{path}", **kw)
        ms = int((time.perf_counter() - t) * 1000)
        key = f"{method.upper()} {path.split('?')[0]}"
        timings[key] = timings.get(key, 0) + ms
        assert r.status_code == expect, f"{key} -> {r.status_code}: {r.text[:300]}"
        if verbose:
            print(f"  {r.status_code} {ms:>6} ms  {method.upper():<5} {path[:90]}")
        return r

    # health + sessions
    assert call("get", "/health").json()["status"] == "ok"
    call("get", "/llm/status")
    up = call("post", "/sessions", files={"file": ("tiny.csv", b"name,email,city\nA,a@x.com,Pune\nB,bad@,Pune\n")}).json()
    assert up["rows"] == 2 and up["stage"] == "loaded"
    s = call("post", "/sessions/demo").json()
    sid = s["session_id"]
    assert s["rows"] == 10200 and s["linked_tables"][0]["name"] == "orders" and s["columns"]
    call("get", "/sessions")
    call("get", f"/sessions/{sid}")
    call("get", f"/sessions/{sid}/warnings", expect=409)  # not scanned yet -> clear error

    # scan + insights
    sc = call("post", f"/sessions/{sid}/scan", json={"overrides": {}}).json()
    assert sc["dimensions"]["clean_rows"] < 90 and sc["pii_columns"] >= 3
    w = call("get", f"/sessions/{sid}/warnings").json()
    assert w and w[0]["severity"] == "high"
    call("get", f"/sessions/{sid}/issues?type=fd_violation&limit=5")
    d = call("get", f"/sessions/{sid}/diagnosis?narrative={'true' if live else 'false'}").json()
    assert any("71 of 73" in x["title"] for x in d["causes"])
    hm = call("get", f"/sessions/{sid}/heatmap?blocks=40").json()
    assert len(hm["cells"]) == 40 and hm["columns"][-1] == "(duplicates)"
    assert call("get", f"/sessions/{sid}/rules").json()
    rows = call("get", f"/sessions/{sid}/rows?limit=5&issue_type=invalid_format&column=pin").json()
    assert rows["total"] >= 31 and rows["rows"][0]["cell_state"]["pin"] == "issue"

    # plan + review
    pl = call("post", f"/sessions/{sid}/repair/plan", json={}).json()
    assert pl["auto"] > 1000 and pl["refused"] > 0
    pr = call("get", f"/sessions/{sid}/proposals?tier=review&sort=confidence&limit=3").json()
    assert pr["total"] > 100 and pr["items"][0]["record_id"]
    groups = call("get", f"/sessions/{sid}/proposals/groups?tier=review").json()
    assert groups and groups[0]["count"] >= 1
    p412 = call("get", f"/sessions/{sid}/proposals?column=pin&limit=1000").json()["items"]
    p412 = next(p for p in p412 if p["row_id"] == 412)
    assert p412["candidates"][0]["value"] == "400001"
    call("get", f"/sessions/{sid}/proposals/{p412['proposal_id']}/explain")
    auto = call("post", f"/sessions/{sid}/repair/apply-auto").json()
    assert auto["applied"] > 1000 and len(auto["checkpoints"]) == 5  # duplicate merges are review items
    pend = [p for p in pr["items"] if p["status"] == "pending"]
    call("post", f"/sessions/{sid}/review/{pend[0]['proposal_id']}", json={"action": "accept"})
    call("post", f"/sessions/{sid}/review/{pend[1]['proposal_id']}", json={"action": "reject"})
    call("post", f"/sessions/{sid}/review/bulk", json={"proposal_ids": groups[0]["proposal_ids"][:5], "action": "accept"})
    call("post", f"/sessions/{sid}/review/NOPE", json={"action": "accept"}, expect=404)
    det = call("get", f"/sessions/{sid}/row/412").json()
    assert det["values"]["pin"] == "400001" and det["record_id"] == "C-10413"
    diff = call("get", f"/sessions/{sid}/rows?view=diff&limit=3").json()
    assert diff["rows"] and diff["rows"][0]["original"]

    # history
    cps = call("get", f"/sessions/{sid}/checkpoints").json()
    assert cps[0]["label"] == "Original" and all(k["active"] for k in cps)
    ch = call("get", f"/sessions/{sid}/changes?row_id=412").json()
    cid = ch["items"][0]["change_id"]
    call("post", f"/sessions/{sid}/changes/{cid}/undo")
    assert call("get", f"/sessions/{sid}/row/412").json()["values"]["pin"] == "40001"
    call("post", f"/sessions/{sid}/checkpoints/K00/restore")
    call("post", f"/sessions/{sid}/checkpoints/{cps[-1]['checkpoint_id']}/restore")
    call("post", f"/sessions/{sid}/checkpoints/K02/undo")
    call("post", f"/sessions/{sid}/checkpoints/K02/restore")
    call("post", f"/sessions/{sid}/checkpoints/{cps[-1]['checkpoint_id']}/restore")  # forward to latest again
    city_changes = [x["change_id"] for x in call("get", f"/sessions/{sid}/changes?column=city&action=apply&limit=1000").json()["items"]]
    call("post", f"/sessions/{sid}/changes/undo", json={"change_ids": city_changes[:3]})
    assert call("get", f"/sessions/{sid}/audit/verify").json()["valid"]

    # privacy, chat
    pv = call("get", f"/sessions/{sid}/privacy").json()
    assert any(f["column"] == "notes" and f["pii_type"] == "aadhaar" for f in pv)
    call("post", f"/sessions/{sid}/privacy/mask", json={"column": "notes", "method": "partial"})
    call("post", f"/sessions/{sid}/privacy/mask", json={"column": "nope", "method": "partial"}, expect=409)
    for q in ["How many customers are in Pune?", "Why did row 52 change?", "Which repairs are you least sure about?",
              "Show duplicates in the email column", "Undo the city fixes"]:
        r = call("post", f"/sessions/{sid}/chat", json={"message": q}).json()
        assert r["text"] and r["tool_calls"], (q, r)
        if verbose:
            print(f"      [{r['mode']}] {q} -> {r['text'][:140]}")
        if "Undo" in q:
            assert r["proposed_action"], r
        if "Pune" in q:
            assert any(ch.isdigit() for ch in r["text"])

    # proof + export
    v = call("get", f"/sessions/{sid}/validation").json()
    assert v["passed"], [x for x in v["checks"] if not x["passed"]]
    b = call("post", f"/sessions/{sid}/benchmark", json={"sample_rows": 1000}).json()
    assert b["repair"]["false_repair_rate"] <= 0.005
    z = call("get", f"/sessions/{sid}/export/zip")
    assert len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 7
    for kind in ("cleaned_csv", "highlighted_xlsx", "report_html", "change_log_csv", "privacy_csv", "recipe_json"):
        assert call("get", f"/sessions/{sid}/export/{kind}").content
    call("get", f"/sessions/{sid}/export/nope", expect=404)
    call("get", "/sessions/doesnotexist", expect=404)
    assert call("get", "/debug/inflight").json() == []

    # persistence: a fresh registry reloads the pickled session
    from api.registry import Registry, registry
    registry.flush()  # saves are debounced in the background
    fresh = Registry(registry.dir)
    assert fresh.get(sid).verify_audit()["valid"]
    return timings


if __name__ == "__main__":
    t = run(live="--live" in sys.argv)
    print(f"\nSMOKE OK · {len(t)} endpoints · slowest: " +
          ", ".join(f"{k} {ms} ms" for k, ms in sorted(t.items(), key=lambda kv: -kv[1])[:5]))
