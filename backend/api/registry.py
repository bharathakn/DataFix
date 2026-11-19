"""In-memory session registry, pickled to disk after every change so a restart mid-demo loses nothing."""
import os
import threading
from pathlib import Path

from datafix.session import Session

ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = Path(os.getenv("DATAFIX_SESSION_DIR", "backend/.sessions"))
if not SESSION_DIR.is_absolute():
    SESSION_DIR = ROOT / SESSION_DIR


class NotFound(KeyError):
    pass


class Registry:
    def __init__(self, directory: Path = SESSION_DIR):
        self.dir = directory
        self.sessions: dict[str, Session] = {}
        self.locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def add(self, s: Session) -> Session:
        with self._guard:
            self.sessions[s.session_id] = s
            self.locks[s.session_id] = threading.RLock()
        self.save(s)
        return s

    def get(self, sid: str) -> Session:
        if sid not in self.sessions:
            path = self.dir / f"{sid}.pkl"
            if not sid.isalnum() or not path.exists():
                raise NotFound(sid)
            with self._guard:
                if sid not in self.sessions:
                    self.sessions[sid] = Session.load(path)
                    self.locks[sid] = threading.RLock()
        return self.sessions[sid]

    def lock(self, sid: str) -> threading.RLock:
        self.get(sid)
        return self.locks[sid]

    def save(self, s: Session) -> None:
        s.save(self.dir)

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.dir.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
            sid = p.stem
            s = self.sessions.get(sid)
            out.append({"session_id": sid, "loaded": s is not None,
                        "filename": s.files[s.main]["filename"] if s else None, "modified": p.stat().st_mtime})
        return out


registry = Registry()
