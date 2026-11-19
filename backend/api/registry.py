"""In-memory session registry, pickled to disk shortly after every change so a restart mid-demo loses nothing."""
import atexit
import os
import threading
import time
from pathlib import Path

from datafix.session import Session

ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = Path(os.getenv("DATAFIX_SESSION_DIR", "backend/.sessions"))
if not SESSION_DIR.is_absolute():
    SESSION_DIR = ROOT / SESSION_DIR


# Delete sessions (memory and disk) untouched for this many hours; 0 keeps them forever (local default).
SESSION_TTL_H = float(os.getenv("DATAFIX_SESSION_TTL_H", "0") or 0)


class NotFound(KeyError):
    pass


class Registry:
    def __init__(self, directory: Path = SESSION_DIR):
        self.dir = directory
        self.sessions: dict[str, Session] = {}
        self.locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()
        self._pending: dict[str, threading.Timer] = {}
        atexit.register(self.flush)

    def prune(self) -> int:
        """Drop sessions idle longer than DATAFIX_SESSION_TTL_H (a public server must not keep uploads forever)."""
        if SESSION_TTL_H <= 0 or not self.dir.exists():
            return 0
        cutoff = time.time() - SESSION_TTL_H * 3600
        removed = 0
        for p in list(self.dir.glob("*.pkl")):
            try:
                if p.stat().st_mtime >= cutoff:
                    continue
                p.unlink()
            except FileNotFoundError:
                continue
            with self._guard:
                self.sessions.pop(p.stem, None)
                self.locks.pop(p.stem, None)
            removed += 1
        return removed

    def add(self, s: Session) -> Session:
        self.prune()
        with self._guard:
            self.sessions[s.session_id] = s
            self.locks[s.session_id] = threading.RLock()
        s.save(self.dir)  # first save is synchronous so a reload right away finds it
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

    SAVE_DELAY_S = 1.5

    def save(self, s: Session) -> None:
        """Debounced background save: a burst of review clicks costs one pickle (≈ 0.6 s), off the request path."""
        sid = s.session_id
        with self._guard:
            if sid in self._pending:
                return  # the pending save will write the latest state
            t = threading.Timer(self.SAVE_DELAY_S, self._save_now, args=(sid,))
            t.daemon = True
            self._pending[sid] = t
        t.start()

    def _save_now(self, sid: str) -> None:
        with self._guard:
            self._pending.pop(sid, None)
        s = self.sessions.get(sid)
        if s is not None:
            with self.locks[sid]:
                s.save(self.dir)

    def flush(self) -> None:
        with self._guard:
            pending = list(self._pending)
            for t in self._pending.values():
                t.cancel()
            self._pending.clear()
        for sid in pending:
            s = self.sessions.get(sid)
            if s is not None:
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
