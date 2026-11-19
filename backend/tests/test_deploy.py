"""Settings a public deployment relies on: hidden session list, expiring sessions, upload limit."""
import os
import time

from fastapi.testclient import TestClient


def test_public_mode_hides_session_list(monkeypatch):
    from api.main import app
    c = TestClient(app)
    monkeypatch.delenv("DATAFIX_PUBLIC", raising=False)
    assert c.get("/api/sessions").status_code == 200
    monkeypatch.setenv("DATAFIX_PUBLIC", "1")
    assert c.get("/api/sessions").status_code == 404


def test_prune_removes_idle_sessions(tmp_path, monkeypatch):
    import api.registry as reg
    r = reg.Registry(tmp_path)
    old, new = tmp_path / "aaaaaaaaaaaa.pkl", tmp_path / "bbbbbbbbbbbb.pkl"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))
    monkeypatch.setattr(reg, "SESSION_TTL_H", 0)
    assert r.prune() == 0 and old.exists()  # 0 = keep forever (local default)
    monkeypatch.setattr(reg, "SESSION_TTL_H", 24)
    assert r.prune() == 1 and not old.exists() and new.exists()


def test_upload_limit(monkeypatch):
    import api.routes as routes
    from api.main import app
    monkeypatch.setattr(routes, "MAX_UPLOAD", 10)
    r = TestClient(app).post("/api/sessions", files={"file": ("x.csv", b"a,b\n1,2\n3,4\n", "text/csv")})
    assert r.status_code == 409 and "larger than" in r.json()["error"]["message"]
