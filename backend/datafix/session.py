"""A cleaning session: read-only originals + append-only change log + checkpoints (docs/03_ARCHITECTURE.md §5).

current(table) = original replayed with every `apply` change whose status is "applied".
Undo / redo / restore never rewrite history; they append entries and flip derived status.
"""
import pickle
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import audit
from .ingest import LoadedTable, load_path
from .models import Change, Checkpoint, RepairProposal
from .planner import plan_repairs
from .scan import ScanResult, scan_table
from .validate import quality_score

DATA_NEUTRAL = {"reject", "reopen", "keep", "unkeep"}

ROW = "__row__"
DELETED = "__deleted__"

# auto-apply batches, in order: (label, predicate on proposal)
AUTO_BATCHES = [
    ("Formats normalised", lambda p: p.repair_class == "normalize"),
    ("Values standardised", lambda p: p.repair_class == "standardize"),
    ("Duplicates merged", lambda p: p.repair_class == "dedupe_merge"),
    ("Spelling & learned-rule fixes", lambda p: p.repair_class == "correct"),
    ("PIN / address recovered", lambda p: p.repair_class == "recover" and p.algorithm in ("pin_recovery", "fill_from_rules")),
    ("Contacts recovered", lambda p: p.repair_class == "recover" and p.algorithm in ("phone_recovery", "email_recovery")),
]

SOURCE_OF_SIGNAL = {
    "fd_majority": "learned_rule", "reference_pin": "india_post_directory", "locality_match": "india_post_directory",
    "row_context": "own_row", "linked_table_match": "linked_table", "records_agree": "linked_table",
    "prefix_match": "own_value", "deterministic_transform": "deterministic", "format_variant": "own_data",
    "alias_dictionary": "alias_dictionary", "string_similarity": "own_data", "vocab_frequency": "own_data",
    "group_statistic": "own_data_statistics", "record_match": "own_data", "pattern_fix": "typo_pattern",
    "known_domain": "domain_list", "crossfield_rule": "learned_rule",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Session:
    def __init__(self, tables: dict[str, LoadedTable], main: str | None = None, thresholds: dict | None = None):
        self.session_id = uuid.uuid4().hex[:12]
        self.created_at = _now()
        self.main = main or next(iter(tables))
        self.files = {n: {"filename": t.filename, "sha256": t.sha256} for n, t in tables.items()}
        self.originals: dict[str, pd.DataFrame] = {n: t.df for n, t in tables.items()}
        self.thresholds = thresholds
        self.scans: dict[str, ScanResult] = {}
        self.proposals: dict[str, RepairProposal] = {}
        self.changes: list[Change] = []
        self.checkpoints: list[Checkpoint] = []
        self.genesis = audit.genesis_hash({n: f["sha256"] for n, f in self.files.items()})
        self._cache: dict[str, tuple[int, pd.DataFrame]] = {}  # materialised current() views
        # working state per table: (version, all rows with applied cell edits, removed row ids, dropped columns)
        self._base: dict[str, tuple[int, pd.DataFrame, set, list]] = {}
        self._version = 0
        self.salt = uuid.uuid4().hex  # per-session key for privacy hashing
        self.privacy: list[dict] = []
        self.validation: dict | None = None
        self.causes: list[dict] | None = None
        self.benchmark_result: dict | None = None
        self.validation_version = -1
        self.columns: dict[str, dict] = {}  # table -> {column: ColumnInfo}, inferred before scanning

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_paths(cls, paths: dict[str, str], thresholds: dict | None = None) -> "Session":
        s = cls({n: load_path(p) for n, p in paths.items()}, thresholds=thresholds)
        s.scan()
        s.plan()
        return s

    def profile(self) -> dict[str, dict]:
        """Column types for every table, inferred once (the user may override before scanning)."""
        from .coltypes import infer_columns
        from .reference import pin_reference
        for n, df in self.originals.items():
            if n not in self.columns and n in getattr(self, "_reuse_columns", {}):
                self.columns[n] = self._reuse_columns[n]
            if n not in self.columns:
                self.columns[n] = infer_columns(df, pin_reference())
        return self.columns

    def scan(self, overrides: dict[str, str] | None = None, reuse: dict[str, ScanResult] | None = None) -> dict[str, ScanResult]:
        if self.changes:
            raise ValueError("repairs have already been applied; start a new session to re-scan")
        self.profile()
        for col, t in (overrides or {}).items():
            info = self.columns[self.main].get(col)
            if info is None:
                raise ValueError(f"unknown column {col!r}")
            info.semantic_type, info.type_confidence, info.overridden = t, 1.0, True
        self.scans = {n: (reuse[n] if reuse and n in reuse else scan_table(df, n, columns=self.columns[n]))
                      for n, df in self.originals.items()}
        self.checkpoints = []
        self.proposals = {}
        self.causes = None
        self.privacy = []
        if not self.checkpoints:
            self.checkpoints.append(Checkpoint("K00", "Original", "original", [], _now(), self.score()))
        return self.scans

    def plan(self) -> list[RepairProposal]:
        props = plan_repairs(self.originals, self.scans, self.thresholds)
        self.proposals = {p.proposal_id: p for p in props}
        return props

    # ------------------------------------------------------------------ state
    def _base_state(self, table: str) -> tuple[int, pd.DataFrame, set, list]:
        """Working table kept in sync by _append; rebuilt by replaying the log only after undo/redo."""
        bases = self.__dict__.setdefault("_base", {})
        b = bases.get(table)
        if b and b[0] == self._version:
            return b
        df = self.originals[table].copy()
        rows: set = set()
        cols: list = []
        for c in self.changes:
            if c.action != "apply" or c.status != "applied" or c.table != table:
                continue
            if c.algorithm == "privacy_drop":
                cols.append(c.column)
            elif c.column == ROW:
                rows.add(c.row_id)
            else:
                df.at[c.row_id, c.column] = c.new_value
        b = (self._version, df, rows, cols)
        bases[table] = b
        return b

    def current(self, table: str | None = None) -> pd.DataFrame:
        table = table or self.main
        cached = self._cache.get(table)
        if cached and cached[0] == self._version:
            return cached[1]
        _, df, rows, cols = self._base_state(table)
        out = df.drop(index=sorted(rows)) if rows else df  # materialise row removals lazily (one copy per read)
        drop_cols = [c for c in cols if c in out.columns]
        if drop_cols:
            out = out.drop(columns=drop_cols)
        self._cache[table] = (self._version, out)
        return out

    def dropped_columns(self, table: str | None = None) -> list[str]:
        table = table or self.main
        return [c.column for c in self.changes if c.action == "apply" and c.status == "applied"
                and c.table == table and c.algorithm == "privacy_drop"]

    def applied_changes(self, table: str | None = None) -> list[Change]:
        return [c for c in self.changes if c.action == "apply" and c.status == "applied"
                and (table is None or c.table == table)]

    def remaining_issues(self, table: str | None = None) -> tuple[list, int]:
        """Scan issues not yet resolved by an applied change, and the current row count (fast, no re-scan)."""
        table = table or self.main
        applied = self.applied_changes(table)
        changed = {(c.row_id, c.column) for c in applied if c.column != ROW}
        dropped = {c.row_id for c in applied if c.column == ROW}
        remaining = [i for i in self.scans[table].issues if i.row_id is not None and i.row_id not in dropped
                     and (i.column is None or (i.row_id, i.column) not in changed)]
        return remaining, len(self.originals[table]) - len(dropped)

    def score(self, table: str | None = None) -> float:
        """Quality score with resolved issues removed (fast estimate; validation re-scans)."""
        remaining, n_rows = self.remaining_issues(table)
        return quality_score(remaining, n_rows, len(self.originals[table or self.main].columns))

    def dimensions_now(self, table: str | None = None) -> dict:
        from .validate import dimensions
        remaining, n_rows = self.remaining_issues(table)
        return dimensions(remaining, n_rows)

    # ------------------------------------------------------------------ log primitives
    def _append(self, change: Change) -> Change:
        prev = self.changes[-1].hash if self.changes else self.genesis
        self.changes.append(audit.seal(change, prev))
        bases = self.__dict__.setdefault("_base", {})
        b = bases.get(change.table)
        self._version += 1
        if change.action == "apply" and b and b[0] == self._version - 1:
            _, df, rows, cols = b  # apply in place instead of replaying the whole log
            if change.algorithm == "privacy_drop":
                cols = cols + [change.column]
            elif change.column == ROW:
                rows.add(change.row_id)
            else:
                df.at[change.row_id, change.column] = change.new_value
            bases[change.table] = (self._version, df, rows, cols)
        neutral = change.action in DATA_NEUTRAL  # decisions that leave every cell as it is
        for t, bt in list(bases.items()):
            if (neutral or t != change.table) and bt[0] == self._version - 1:
                bases[t] = (self._version, *bt[1:])  # other tables are unaffected
        for t, (ver, df) in list(self._cache.items()):
            if (neutral or t != change.table) and ver == self._version - 1:
                self._cache[t] = (self._version, df)
        return change

    def _new_checkpoint(self, label: str, kind: str) -> Checkpoint:
        k = Checkpoint(f"K{len(self.checkpoints):02d}", label, kind, [], _now(), 0.0)
        self.checkpoints.append(k)
        return k

    def _review_checkpoint(self) -> Checkpoint:
        last = self.checkpoints[-1]
        return last if last.kind == "review" else self._new_checkpoint("Review decisions", "review")

    def _cell(self, table: str, row: int, col: str) -> str:
        _, df, _, cols = self._base_state(table)
        if col in cols or col not in df.columns:
            return ""
        return df.at[row, col]

    def _record(self, k: Checkpoint, p: RepairProposal | None, table: str, row: int, col: str, new: str,
                reason: str, evidence: list[str], source: str, conf: float, algorithm: str, actor: str) -> Change:
        old = self._cell(table, row, col) if col != ROW else ""
        c = Change(f"C{len(self.changes) + 1:05d}", k.checkpoint_id, p.proposal_id if p else None, table, int(row),
                   col, old, new, reason, evidence, source, round(conf, 4), algorithm, actor, "apply", None, _now())
        self._append(c)
        k.change_ids.append(c.change_id)
        return c

    # ------------------------------------------------------------------ applying proposals
    def _issue_index(self, table: str) -> dict:
        cache = self.__dict__.setdefault("_issue_idx", {})
        if table not in cache:
            cache[table] = {i.issue_id: i for i in self.scans[table].issues}
        return cache[table]

    def _reason(self, p: RepairProposal) -> str:
        idx = self._issue_index(p.table)
        msgs = [idx[i].message for i in p.issue_ids if i in idx]
        return msgs[0] if msgs else p.repair_class

    def apply_proposal(self, pid: str, candidate_index: int = 0, custom_value: str | None = None,
                       actor: str = "user", checkpoint: Checkpoint | None = None, rescore: bool = True) -> list[Change]:
        p = self.proposals[pid]
        if p.status == "applied":
            raise ValueError(f"{pid} is already applied")
        if custom_value is None and not p.candidates:
            raise ValueError(f"{pid} has no candidate to apply ({p.tier})")
        k = checkpoint or self._review_checkpoint()
        if custom_value is not None:
            value, conf, signals = custom_value, 1.0, []
            evidence, source = ["value entered by reviewer"], "reviewer"
        else:
            cand = p.candidates[candidate_index]
            value, conf, signals = cand.value, cand.confidence, cand.signals
            evidence = [s.detail for s in signals if not s.conflicting]
            source = " + ".join(dict.fromkeys(SOURCE_OF_SIGNAL.get(s.name, s.name) for s in signals
                                              if not s.conflicting and s.reliability > 0)) or "engine"
        reason = self._reason(p)
        out = []
        if p.column == ROW:
            survivor = p.meta["survivor"]
            for col, val in p.meta.get("fills", {}).items():
                if self._cell(p.table, survivor, col).strip() == "":
                    out.append(self._record(k, p, p.table, survivor, col, val, f"filled from duplicate row {p.row_id}",
                                            evidence, source, conf, p.algorithm, actor))
            for r in p.meta.get("fk_remaps", []):
                out.append(self._record(k, p, r["table"], r["row_id"], r["column"], r["new"],
                                        f"re-pointed to surviving record {r['new']} (duplicate {r['old']} merged)",
                                        evidence, source, conf, p.algorithm, actor))
            out.append(self._record(k, p, p.table, p.row_id, ROW, DELETED, reason, evidence, source, conf,
                                    p.algorithm, actor))
        else:
            out.append(self._record(k, p, p.table, p.row_id, p.column, value, reason, evidence, source, conf,
                                    p.algorithm, actor))
        p.status = "applied"
        p.meta["applied_value"] = value
        p.meta["change_ids"] = [c.change_id for c in out]
        if rescore:  # O(issues); batch callers score once at the end
            k.quality_score = self.score()
        return out

    def apply_auto(self) -> list[Checkpoint]:
        made = []
        for label, pred in AUTO_BATCHES:
            batch = [p for p in self.proposals.values() if p.tier == "auto" and p.status == "pending" and pred(p)]
            if not batch:
                continue
            k = self._new_checkpoint(label, "auto")
            for p in batch:
                self.apply_proposal(p.proposal_id, actor="auto", checkpoint=k, rescore=False)
            k.quality_score = self.score()
            made.append(k)
        return made

    def review(self, pid: str, action: str, candidate_index: int = 0, custom_value: str | None = None) -> list[Change]:
        if action == "accept":
            return self.apply_proposal(pid, 0)
        if action == "choose":
            return self.apply_proposal(pid, candidate_index, custom_value)
        if action == "reject":
            p = self.proposals[pid]
            k = self._review_checkpoint()
            c = Change(f"C{len(self.changes) + 1:05d}", k.checkpoint_id, pid, p.table, p.row_id, p.column,
                       p.original_value, p.original_value, "reviewer rejected the proposed repair", [], "reviewer",
                       0.0, p.algorithm, "user", "reject", None, _now(), status="rejected")
            self._append(c)
            p.status = "rejected"
            return [c]
        raise ValueError(f"unknown review action {action!r}")

    def bulk_review(self, pids: list[str], action: str) -> int:
        n = 0
        for pid in pids:
            if self.proposals[pid].status != "pending":
                continue
            if action == "accept":
                self.apply_proposal(pid, 0, rescore=False)
            else:
                self.review(pid, action)
            n += 1
        if n:
            self.checkpoints[-1].quality_score = self.score()
        return n

    def _accept_all_batch(self, tier: str, column: str | None) -> tuple[list[RepairProposal], list[RepairProposal]]:
        """Pending proposals of a tier that can be accepted together, plus the ones that would collide.
        Cell fixes go first (most confident first, one per cell); merges last, skipping rows already merged away."""
        pending = [p for p in self.proposals.values() if p.tier == tier and p.status == "pending" and p.candidates
                   and (not column or p.column == column)]
        cells = sorted((p for p in pending if p.column != ROW), key=lambda p: -p.confidence)
        merges = sorted((p for p in pending if p.column == ROW), key=lambda p: -p.confidence)
        seen: set = set()
        take, skip = [], []
        for p in cells:
            key = (p.table, p.row_id, p.column)
            (skip if key in seen else take).append(p)
            seen.add(key)
        gone: dict[str, set] = {}
        for p in merges:
            g = gone.setdefault(p.table, set(self._base_state(p.table)[2]))
            if p.row_id in g or p.meta.get("survivor") in g:
                skip.append(p)
                continue
            g.add(p.row_id)
            take.append(p)
        return take, skip

    def accept_all_preview(self, tier: str = "review", column: str | None = None) -> dict:
        take, skip = self._accept_all_batch(tier, column)
        confs = [p.confidence for p in take]
        by_col = Counter("duplicate rows" if p.column == ROW else p.column for p in take)
        return {"count": len(take), "skipped": len(skip), "by_column": dict(by_col.most_common()),
                "avg_confidence": round(sum(confs) / len(confs), 4) if confs else None,
                "min_confidence": round(min(confs), 4) if confs else None,
                "below_80": sum(c < 0.80 for c in confs),
                "expected_wrong": round(sum(1 - c for c in confs)),  # confidence is calibrated, so Σ(1−c) ≈ wrong fixes
                "merges": by_col.get("duplicate rows", 0)}

    def accept_all(self, tier: str = "review", column: str | None = None, actor: str = "user") -> tuple[Checkpoint | None, int, int]:
        """Accept every pending suggestion of a tier (optionally one column) as ONE checkpoint, so one click undoes it."""
        take, skip = self._accept_all_batch(tier, column)
        if not take:
            return None, 0, len(skip)
        what = f"'{column}'" if column and column != ROW else "duplicate-row" if column == ROW else "all"
        k = self._new_checkpoint(f"Accepted {what} {tier} suggestions in bulk ({len(take):,})", "bulk")
        for p in take:
            self.apply_proposal(p.proposal_id, 0, actor=actor, checkpoint=k, rescore=False)
        k.quality_score = self.score()
        return k, len(take), len(skip)

    def reject_all(self, tier: str, column: str | None = None, actor: str = "user") -> list[str]:
        """Decline every pending suggestion of a tier (optionally one column). No cell changes; reopen() reverts it."""
        pids = [p.proposal_id for p in self.proposals.values() if p.tier == tier and p.status == "pending"
                and (not column or p.column == column)]
        k = self._review_checkpoint()
        for pid in pids:
            p = self.proposals[pid]
            self._append(Change(f"C{len(self.changes) + 1:05d}", k.checkpoint_id, pid, p.table, p.row_id, p.column,
                                p.original_value, p.original_value, f"reviewer declined all {tier} items in bulk", [],
                                "reviewer", 0.0, p.algorithm, actor, "reject", None, _now(), status="rejected"))
            p.status = "rejected"
        return pids

    def reopen(self, pids: list[str], actor: str = "user") -> int:
        """Put rejected suggestions back in their queue (the undo of a reject)."""
        k = self._review_checkpoint()
        n = 0
        for pid in pids:
            p = self.proposals[pid]
            if p.status != "rejected":
                continue
            self._append(Change(f"C{len(self.changes) + 1:05d}", k.checkpoint_id, pid, p.table, p.row_id, p.column,
                                p.original_value, p.original_value, "rejection undone: back in the queue", [],
                                "reviewer", 0.0, p.algorithm, actor, "reopen", None, _now(), status="reopened"))
            p.status = "pending"
            n += 1
        return n

    # ------------------------------------------------------------------ undo / redo / time travel
    def _set_status(self, change: Change, applied: bool, actor: str) -> None:
        if (change.status == "applied") == applied:
            return
        change.status = "applied" if applied else "undone"
        self._append(Change(f"C{len(self.changes) + 1:05d}", change.checkpoint_id, change.proposal_id, change.table,
                            change.row_id, change.column, change.new_value if not applied else change.original_value,
                            change.original_value if not applied else change.new_value,
                            f"{'redo' if applied else 'undo'} of {change.change_id}", [], actor, 0.0,
                            change.algorithm, actor, "redo" if applied else "undo", change.change_id, _now()))
        p = self.proposals.get(change.proposal_id or "")
        if p:
            ids = p.meta.get("change_ids", [])
            states = [self._by_id(i).status for i in ids]
            if all(s == "applied" for s in states):
                p.status = "applied"
            else:  # an undone review suggestion still needs a human decision, so it goes back in the queue
                p.status = "pending" if p.tier == "review" and not any(s == "applied" for s in states) else "undone"

    def _by_id(self, change_id: str) -> Change:
        """O(1): ids are sequential (C00001 is entry 1). A linear scan here made History / undo quadratic
        and locked a 160k-entry session for minutes."""
        try:
            c = self.changes[int(change_id[1:]) - 1]
            if c.change_id == change_id:
                return c
        except (ValueError, IndexError):
            pass
        for c in self.changes:  # fallback for any non-standard id
            if c.change_id == change_id:
                return c
        raise KeyError(change_id)

    def undo_change(self, change_id: str, actor: str = "user") -> Change:
        c = self._by_id(change_id)
        if c.action != "apply":
            raise ValueError("only apply entries can be undone")
        p = self.proposals.get(c.proposal_id or "")
        if p and p.column == ROW:  # a merge is all-or-nothing
            for cid in p.meta.get("change_ids", []):
                self._set_status(self._by_id(cid), False, actor)
        else:
            self._set_status(c, False, actor)
        return c

    def undo_checkpoint(self, checkpoint_id: str, actor: str = "user") -> None:
        k = self._checkpoint(checkpoint_id)
        for cid in k.change_ids:
            self._set_status(self._by_id(cid), False, actor)

    def restore(self, checkpoint_id: str, actor: str = "user") -> None:
        """Make exactly the checkpoints up to and including `checkpoint_id` active (works backwards and forwards)."""
        order = [k.checkpoint_id for k in self.checkpoints]
        if checkpoint_id not in order:
            raise KeyError(checkpoint_id)
        cut = order.index(checkpoint_id)
        for i, k in enumerate(self.checkpoints):
            for cid in k.change_ids:
                c = self._by_id(cid)
                if c.action == "apply" and c.status in ("applied", "undone"):
                    self._set_status(c, i <= cut, actor)

    def _checkpoint(self, checkpoint_id: str) -> Checkpoint:
        for k in self.checkpoints:
            if k.checkpoint_id == checkpoint_id:
                return k
        raise KeyError(checkpoint_id)

    def checkpoint_states(self) -> list[dict]:
        out = []
        for k in self.checkpoints:
            applies = [self._by_id(c) for c in k.change_ids]
            active = k.kind == "original" or any(c.status == "applied" for c in applies)
            out.append({**k.to_dict(), "changes": len(applies), "active": active})
        return out

    def verify_audit(self) -> dict:
        return audit.verify(self.changes, self.genesis)

    # ------------------------------------------------------------------ proof, diagnosis, privacy
    def validate(self) -> dict:
        from .doharm import validate_session
        self.validation = validate_session(self)
        self.validation_version = self._version
        return self.validation

    def fresh_validation(self) -> dict:
        return self.validation if self.validation and self.validation_version == self._version else self.validate()

    def undo_changes(self, change_ids: list[str], actor: str = "user") -> int:
        n = 0
        for cid in change_ids:
            c = self._by_id(cid)
            if c.action == "apply" and c.status == "applied":
                self.undo_change(cid, actor)
                n += 1
        return n

    @property
    def version(self) -> int:
        return self._version

    def stage(self) -> str:
        if not self.scans:
            return "loaded"
        if not self.proposals:
            return "scanned"
        return "repairing" if self.changes else "planned"

    def __getstate__(self):
        state = dict(self.__dict__)
        state["_cache"] = {}
        state.pop("_ui_cache", None)
        state.pop("_issue_idx", None)
        state.pop("_base", None)
        return state

    def diagnose(self) -> list[dict]:
        from .diagnose import diagnose
        self.causes = diagnose(self.originals[self.main], self.scans[self.main])
        return self.causes

    def run_benchmark(self, **kwargs) -> dict:
        from .benchmark import run_benchmark
        self.benchmark_result = run_benchmark(self, **kwargs)
        return self.benchmark_result

    def privacy_scan(self) -> list[dict]:
        from .privacy import scan_pii
        self.privacy = [dict(f, table=t) for t in self.originals for f in scan_pii(self.originals[t], self.scans[t].columns)]
        return self.privacy

    def privacy_status(self) -> list[dict]:
        """Findings with masked/method derived from the live change log, so undoing a mask un-marks it."""
        if not self.privacy:
            self.privacy_scan()
        active: dict[tuple[str, str], str] = {}
        for c in self.applied_changes():
            if c.algorithm == "privacy_drop":
                active[(c.table, c.column)] = "drop"
            elif c.algorithm == "privacy_mask":
                active.setdefault((c.table, c.column), c.reason.rsplit(" ", 1)[-1])
        kept = self.privacy_kept()
        out = []
        for f in self.privacy:
            method = active.get((f["table"], f["column"]))
            out.append({**f, "masked": method is not None, "method": method, "kept": (f["table"], f["column"]) in kept})
        return out

    def privacy_kept(self) -> set[tuple[str, str]]:
        """Columns the user chose to leave unmasked, derived from the log (keep / unkeep entries)."""
        kept: set = set()
        for c in self.changes:
            if c.algorithm == "privacy_keep":
                (kept.add if c.action == "keep" else kept.discard)((c.table, c.column))
        return kept

    def keep_unmasked(self, column: str, table: str | None = None, keep: bool = True) -> None:
        """Record that personal data in a column is kept on purpose (or undo that). Changes no cell."""
        table = table or self.main
        if not self.privacy:
            self.privacy_scan()
        if not any(f["table"] == table and f["column"] == column for f in self.privacy):
            raise ValueError(f"no personal data found in {table}.{column}")
        if ((table, column) in self.privacy_kept()) == keep:
            return
        k = self.checkpoints[-1]
        self._append(Change(f"C{len(self.changes) + 1:05d}", k.checkpoint_id, None, table, -1, column, "", "",
                            f"privacy: {column} {'kept unmasked on purpose' if keep else 'no longer marked as kept'}", [],
                            "privacy_shield", 1.0, "privacy_keep", "user", "keep" if keep else "unkeep", None, _now(),
                            status="kept" if keep else "unkept"))

    def mask_column(self, column: str, method: str, table: str | None = None, pii_type: str | None = None) -> Checkpoint:
        """Mask PII in one column as an undoable checkpoint. method: partial | redact | hash | drop."""
        from .privacy import find_spans, mask_text, mask_value
        table = table or self.main
        if not self.privacy:
            self.privacy_scan()
        found = [f for f in self.privacy if f["table"] == table and f["column"] == column
                 and (pii_type is None or f["pii_type"] == pii_type)]
        if not found:
            raise ValueError(f"no personal data found in {table}.{column}")
        k = self._new_checkpoint(f"Privacy: {column} {'dropped' if method == 'drop' else method + ' masked'}", "mask")
        kinds = {f["pii_type"] for f in found}
        if method == "drop":
            c = Change(f"C{len(self.changes) + 1:05d}", k.checkpoint_id, None, table, -1, column, "", "__column_dropped__",
                       f"privacy: column {column} removed ({', '.join(sorted(kinds))})", [], "privacy_shield", 1.0,
                       "privacy_drop", "user", "apply", None, _now())
            self._append(c)
            k.change_ids.append(c.change_id)
        else:
            df = self.current(table)
            free_text = any(f["in_free_text"] for f in found)
            kind = next(iter(kinds))
            for row, x in df[column].items():
                if not x.strip():
                    continue
                if free_text:
                    if not find_spans(x):
                        continue
                    new = mask_text(x, method, self.salt, kinds)
                else:
                    new = mask_value(x, kind, method, self.salt)
                if new != x:
                    self._record(k, None, table, row, column, new, f"privacy: {', '.join(sorted(kinds))} {method}",
                                 [], "privacy_shield", 1.0, "privacy_mask", "user")
        for f in found:
            f["masked"], f["method"] = True, method
        k.quality_score = self.score()
        return k

    # ------------------------------------------------------------------ outputs
    def row_status(self, table: str | None = None) -> pd.Series:
        """_datafix_status per row: needs_review > estimated > repaired > unchanged."""
        table = table or self.main
        df = self.current(table)
        status = pd.Series("unchanged", index=df.index)
        applied = self.applied_changes(table)
        for c in applied:
            if c.column != ROW and c.row_id in status.index:
                status[c.row_id] = "repaired"
        for c in applied:
            p = self.proposals.get(c.proposal_id or "")
            if p and p.repair_class == "impute" and c.row_id in status.index:
                status[c.row_id] = "estimated"
        for p in self.proposals.values():
            if p.table == table and p.status == "pending" and p.tier in ("review", "flag", "refused") \
                    and p.row_id in status.index:
                status[p.row_id] = "needs_review"
        return status

    def cleaned(self, table: str | None = None, with_status: bool = True) -> pd.DataFrame:
        df = self.current(table).copy()
        if with_status:
            df["_datafix_status"] = self.row_status(table)
        return df

    def change_log(self) -> pd.DataFrame:
        rows = []
        id_cols = {t: next((col for col, i in self.scans[t].columns.items()
                            if i.semantic_type == "id" and i.distinct >= 0.95 * len(self.originals[t])), None)
                   for t in self.originals}
        for c in self.changes:
            d = c.to_dict()
            d["evidence"] = " | ".join(c.evidence)
            id_col = id_cols.get(c.table)
            d["record_id"] = self.originals[c.table].at[c.row_id, id_col] if id_col and c.row_id >= 0 else c.row_id
            rows.append(d)
        cols = ["change_id", "checkpoint_id", "action", "status", "table", "row_id", "record_id", "column",
                "original_value", "new_value", "reason", "evidence", "source", "confidence", "algorithm", "actor",
                "target", "proposal_id", "timestamp", "prev_hash", "hash"]
        return pd.DataFrame(rows, columns=cols)

    # ------------------------------------------------------------------ persistence
    def save(self, directory: str | Path) -> Path:
        path = Path(directory) / f"{self.session_id}.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self, f)
        return path

    @staticmethod
    def load(path: str | Path) -> "Session":
        with Path(path).open("rb") as f:
            return pickle.load(f)
