"""Append-only, hash-chained audit log. Editing any past entry breaks verification from that entry on."""
import hashlib
import json

from .models import Change

_EXCLUDED = {"hash", "status"}


def entry_hash(prev_hash: str, change: Change) -> str:
    payload = {k: v for k, v in change.to_dict().items() if k not in _EXCLUDED}
    payload["prev_hash"] = prev_hash
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256((prev_hash + blob).encode("utf-8")).hexdigest()


def genesis_hash(file_fingerprints: dict[str, str]) -> str:
    """Chain starts from the input files' SHA-256, tying the log to exactly those files."""
    blob = json.dumps(file_fingerprints, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def seal(change: Change, prev_hash: str) -> Change:
    change.prev_hash = prev_hash
    change.hash = entry_hash(prev_hash, change)
    return change


def verify(changes: list[Change], genesis: str) -> dict:
    prev = genesis
    for c in changes:
        if c.prev_hash != prev or entry_hash(prev, c) != c.hash:
            return {"valid": False, "entries": len(changes), "broken_at": c.change_id, "head_hash": prev}
        prev = c.hash
    return {"valid": True, "entries": len(changes), "broken_at": None, "head_hash": prev}
