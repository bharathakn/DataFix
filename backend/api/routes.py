"""REST routes (docs/04_API_CONTRACT.md). Thin: every rule lives in the datafix engine."""
import functools
import re
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from datafix import insights
from datafix.chat_tools import answer
from datafix.export import export_bundle, privacy_report, write_highlighted_xlsx, write_report
from datafix.ingest import load_bytes, load_path
from datafix.llm import causes_narrative, explain_proposal, get_llm
from datafix.recipe import build_recipe
from datafix.repair import find_joins
from datafix.session import Session

from .registry import ROOT, registry

router = APIRouter(prefix="/api")
DEMO = ROOT / "data" / "demo"
MAX_UPLOAD = 200 * 1024 * 1024


# ---------------------------------------------------------------- helpers
def locked(fn):
    """Hold the session's (re-entrant) lock for the whole request. Reads must not interleave with a repair:
    the current-table cache is updated in place and pandas is not thread-safe."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with registry.lock(kwargs["sid"]):
            return fn(*args, **kwargs)
    return wrapper


def _table_name(filename: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", Path(filename or "").stem).strip("_").lower()
    return stem or fallback


def _summary(s: Session) -> dict:
    cols = s.scans[s.main].columns if s.scans else s.profile()[s.main]
    linked = []
    for n in s.originals:
        if n == s.main:
            continue
        joins = find_joins(s.scans[s.main], s.scans[n]) if s.scans else []
        linked.append({"name": n, "rows": len(s.originals[n]), "join_key": joins[0][0] if joins else None})
    out = {"session_id": s.session_id, "table": s.main, "filename": s.files[s.main]["filename"],
           "rows": len(s.originals[s.main]), "rows_current": len(s.current()) if s.scans else len(s.originals[s.main]),
           "columns": [i.to_dict() for i in cols.values()], "linked_tables": linked,
           "file_sha256": s.files[s.main]["sha256"], "created_at": s.created_at, "stage": s.stage(),
           "version": s.version}
    if s.scans:
        scan = s.scans[s.main]
        from collections import Counter
        from datafix.validate import dimensions
        out["quality_score"] = scan.quality_score
        out["score_now"] = s.score()
        out["counts"] = scan.counts
        out["dimensions"] = dimensions(scan.issues, len(s.originals[s.main]))
        out["dimensions_now"] = s.dimensions_now()
        out["pii_columns"] = len({(f["table"], f["column"]) for f in s.privacy})
        mine = [p for p in s.proposals.values() if p.table == s.main]
        out["tiers"] = dict(Counter(p.tier for p in s.proposals.values()))
        out["pending"] = dict(Counter(p.tier for p in s.proposals.values() if p.status == "pending"))
        out["applied"] = sum(1 for p in s.proposals.values() if p.status == "applied")
        out["checkpoints"] = len(s.checkpoints)
        out["rows_main_pending"] = len({p.row_id for p in mine if p.status == "pending" and p.tier != "auto"})
    return out


def _session(sid: str) -> Session:
    return registry.get(sid)


def _id_col(s: Session, table: str) -> str | None:
    if not s.scans:
        return None
    return next((c for c, i in s.scans[table].columns.items()
                 if i.semantic_type == "id" and i.distinct >= 0.95 * len(s.originals[table])), None)


def _record_id(s: Session, table: str, row: int):
    col = _id_col(s, table)
    return s.originals[table].at[row, col] if col and row in s.originals[table].index else row


def _require_scan(s: Session):
    if not s.scans:
        raise ValueError("scan the session first (POST /scan)")


def _require_plan(s: Session):
    _require_scan(s)
    if not s.proposals:
        raise ValueError("plan repairs first (POST /repair/plan)")


# ---------------------------------------------------------------- sessions
@router.get("/sessions")
def list_sessions():
    return registry.list()


@router.post("/sessions")
async def create_session(file: UploadFile = File(...), linked_file: UploadFile | None = File(None),
                         linked_name: str | None = Form(None)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise ValueError("file is larger than 200 MB")
    tables = {_table_name(file.filename, "data"): load_bytes(data, file.filename or "data.csv")}
    if linked_file is not None and linked_file.filename:
        ldata = await linked_file.read()
        name = _table_name(linked_name or linked_file.filename, "linked")
        if name in tables:
            name += "_linked"
        tables[name] = load_bytes(ldata, linked_file.filename)
    s = Session(tables)
    s.profile()
    return _summary(registry.add(s))


@router.post("/sessions/demo")
def create_demo():
    s = Session({"customers": load_path(DEMO / "customers_dirty.csv"), "orders": load_path(DEMO / "orders.csv")})
    s.profile()
    return _summary(registry.add(s))


@router.get("/sessions/{sid}")
@locked
def get_session(sid: str):
    return _summary(_session(sid))


@router.get("/sessions/{sid}/rows")
@locked
def get_rows(sid: str, offset: int = 0, limit: int = Query(100, le=500),
             view: Literal["current", "original", "diff"] = "current", table: str | None = None,
             issue_type: str | None = None, column: str | None = None, state: str | None = None,
             row_ids: str | None = None):
    s = _session(sid)
    with registry.lock(sid):
        ids = [int(x) for x in row_ids.split(",") if x.strip().isdigit()] if row_ids else None
        return insights.rows_page(s, table or s.main, view, offset, limit, issue_type, column, state, ids)


@router.get("/sessions/{sid}/row/{row_id}")
@locked
def get_row(sid: str, row_id: int, table: str | None = None):
    s = _session(sid)
    _require_scan(s)
    with registry.lock(sid):
        d = insights.row_detail(s, table or s.main, row_id)
        d["record_id"] = _record_id(s, table or s.main, row_id)
        return d


# ---------------------------------------------------------------- scan & insights
class ScanBody(BaseModel):
    overrides: dict[str, str] = Field(default_factory=dict)


@router.post("/sessions/{sid}/scan")
@locked
def scan(sid: str, body: ScanBody | None = None):
    s = _session(sid)
    with registry.lock(sid):
        scans = s.scan((body or ScanBody()).overrides)
        s.diagnose()
        s.privacy_scan()
        registry.save(s)
        res = scans[s.main]
        from datafix.validate import dimensions
        return {"quality_score": res.quality_score, "dimensions": dimensions(res.issues, res.n_rows),
                "counts": res.counts, "by_column": res.by_column,
                "pii_columns": len({(f["table"], f["column"]) for f in s.privacy}),
                "warnings": len(insights.warnings(res, res.n_rows)), "rules": len(res.rules),
                "duration_ms": sum(r.timings_ms.get("total", 0) for r in scans.values()),
                "tables": {n: {"rows": r.n_rows, "quality_score": r.quality_score, "counts": r.counts}
                           for n, r in scans.items()}}


@router.get("/sessions/{sid}/issues")
@locked
def issues(sid: str, type: str | None = None, column: str | None = None, table: str | None = None,
           offset: int = 0, limit: int = Query(100, le=1000)):
    s = _session(sid)
    _require_scan(s)
    items = [i.to_dict() for i in s.scans[table or s.main].issues
             if (not type or i.type == type) and (not column or i.column == column)]
    return {"total": len(items), "items": items[offset:offset + limit]}


@router.get("/sessions/{sid}/warnings")
@locked
def warnings(sid: str, table: str | None = None):
    s = _session(sid)
    _require_scan(s)
    t = table or s.main
    return insights.warnings(s.scans[t], len(s.originals[t]))


@router.get("/sessions/{sid}/diagnosis")
@locked
def diagnosis(sid: str, narrative: bool = False):
    s = _session(sid)
    _require_scan(s)
    with registry.lock(sid):
        causes = s.causes if s.causes is not None else s.diagnose()
    text, mode = causes_narrative(causes) if narrative else (None, None)
    return {"causes": causes, "narrative": text, "mode": mode}


@router.get("/sessions/{sid}/heatmap")
@locked
def heatmap(sid: str, blocks: int = Query(50, ge=1, le=200), table: str | None = None):
    s = _session(sid)
    _require_scan(s)
    t = table or s.main
    return insights.heatmap(s.scans[t], len(s.originals[t]), list(s.originals[t].columns), blocks)


@router.get("/sessions/{sid}/rules")
@locked
def rules(sid: str, table: str | None = None):
    s = _session(sid)
    _require_scan(s)
    return [r.to_dict() for r in s.scans[table or s.main].rules]


# ---------------------------------------------------------------- repair
class Thresholds(BaseModel):
    auto: float = Field(0.95, ge=0.5, le=1.0)
    review: float = Field(0.70, ge=0.0, le=1.0)


class PlanBody(BaseModel):
    thresholds: Thresholds | None = None


@router.post("/sessions/{sid}/repair/plan")
@locked
def plan(sid: str, body: PlanBody | None = None):
    s = _session(sid)
    _require_scan(s)
    with registry.lock(sid):
        if s.changes:
            raise ValueError("repairs already applied; undo them or start a new session to re-plan")
        if body and body.thresholds:
            s.thresholds = body.thresholds.model_dump()
        import time
        t0 = time.perf_counter()
        props = s.plan()
        registry.save(s)
        from datafix.planner import summarize
        summ = summarize(props)
        from collections import Counter
        return {**summ["tiers"], "tiers": summ["tiers"],
                "by_class": dict(Counter(p.repair_class for p in props)),
                "duration_ms": int((time.perf_counter() - t0) * 1000)}


@router.get("/sessions/{sid}/proposals")
@locked
def proposals(sid: str, tier: str | None = None, column: str | None = None, status: str | None = None,
              table: str | None = None, algorithm: str | None = None,
              sort: Literal["row", "confidence", "-confidence"] = "row",
              offset: int = 0, limit: int = Query(100, le=1000)):
    s = _session(sid)
    _require_plan(s)
    ps = [p for p in s.proposals.values() if (not tier or p.tier == tier) and (not column or p.column == column)
          and (not status or p.status == status) and (not table or p.table == table)
          and (not algorithm or p.algorithm == algorithm)]
    if sort == "row":
        ps.sort(key=lambda p: (p.table != s.main, p.row_id))
    else:
        ps.sort(key=lambda p: (p.confidence, p.row_id), reverse=sort == "-confidence")
    items = []
    for p in ps[offset:offset + limit]:
        d = p.to_dict()
        d["record_id"] = _record_id(s, p.table, p.row_id)
        items.append(d)
    return {"total": len(ps), "items": items}


@router.get("/sessions/{sid}/proposals/groups")
@locked
def proposal_groups(sid: str, tier: str | None = "review", column: str | None = None):
    s = _session(sid)
    _require_plan(s)
    return insights.proposal_groups(s, tier, column)


@router.get("/sessions/{sid}/proposals/{pid}/explain")
@locked
def explain(sid: str, pid: str):
    s = _session(sid)
    _require_plan(s)
    text, mode = explain_proposal(s.proposals[pid])
    return {"text": text, "mode": mode}


@router.post("/sessions/{sid}/repair/apply-auto")
@locked
def apply_auto(sid: str):
    s = _session(sid)
    _require_plan(s)
    with registry.lock(sid):
        made = s.apply_auto()
        registry.save(s)
        return {"checkpoints": [k.to_dict() for k in made], "applied": sum(len(k.change_ids) for k in made),
                "score_now": s.score()}


class BulkBody(BaseModel):
    proposal_ids: list[str]
    action: Literal["accept", "reject"]


@router.post("/sessions/{sid}/review/bulk")
@locked
def review_bulk(sid: str, body: BulkBody):
    s = _session(sid)
    _require_plan(s)
    with registry.lock(sid):
        before = {pid: s.proposals[pid].status for pid in body.proposal_ids}
        n = s.bulk_review(body.proposal_ids, body.action)
        registry.save(s)
        k = s.checkpoints[-1]
        change_ids = [cid for pid in body.proposal_ids if before[pid] == "pending" and s.proposals[pid].status == "applied"
                      for cid in s.proposals[pid].meta.get("change_ids", [])]
        return {"applied": n, "change_ids": change_ids, "checkpoint": k.to_dict(), "score_now": s.score()}


class ReviewBody(BaseModel):
    action: Literal["accept", "reject", "choose"]
    candidate_index: int = 0
    custom_value: str | None = None


@router.post("/sessions/{sid}/review/{pid}")
@locked
def review(sid: str, pid: str, body: ReviewBody):
    s = _session(sid)
    _require_plan(s)
    with registry.lock(sid):
        changes = s.review(pid, body.action, body.candidate_index, body.custom_value)
        registry.save(s)
        return {"proposal": s.proposals[pid].to_dict(), "changes": [c.to_dict() for c in changes],
                "score_now": s.score()}


# ---------------------------------------------------------------- history
@router.get("/sessions/{sid}/checkpoints")
@locked
def checkpoints(sid: str):
    return _session(sid).checkpoint_states()


@router.post("/sessions/{sid}/checkpoints/{cid}/restore")
@locked
def restore(sid: str, cid: str):
    s = _session(sid)
    with registry.lock(sid):
        s.restore(cid)
        registry.save(s)
        return s.checkpoint_states()


@router.post("/sessions/{sid}/checkpoints/{cid}/undo")
@locked
def undo_checkpoint(sid: str, cid: str):
    s = _session(sid)
    with registry.lock(sid):
        s.undo_checkpoint(cid)
        registry.save(s)
        return s.checkpoint_states()


@router.post("/sessions/{sid}/changes/{change_id}/undo")
@locked
def undo_change(sid: str, change_id: str):
    s = _session(sid)
    with registry.lock(sid):
        c = s.undo_change(change_id)
        registry.save(s)
        return c.to_dict()


class UndoBody(BaseModel):
    change_ids: list[str]


@router.post("/sessions/{sid}/changes/undo")
@locked
def undo_many(sid: str, body: UndoBody):
    s = _session(sid)
    with registry.lock(sid):
        n = s.undo_changes(body.change_ids)
        registry.save(s)
        return {"undone": n, "checkpoints": s.checkpoint_states()}


@router.get("/sessions/{sid}/changes")
@locked
def changes(sid: str, row_id: int | None = None, column: str | None = None, checkpoint_id: str | None = None,
            action: str | None = None, table: str | None = None, offset: int = 0, limit: int = Query(100, le=1000)):
    s = _session(sid)
    cs = [c for c in s.changes if (row_id is None or c.row_id == row_id) and (not column or c.column == column)
          and (not checkpoint_id or c.checkpoint_id == checkpoint_id) and (not action or c.action == action)
          and (not table or c.table == table)]
    items = []
    for c in cs[offset:offset + limit]:
        d = c.to_dict()
        d["record_id"] = _record_id(s, c.table, c.row_id) if c.row_id >= 0 else None
        items.append(d)
    return {"total": len(cs), "items": items}


@router.get("/sessions/{sid}/audit/verify")
@locked
def audit_verify(sid: str):
    return _session(sid).verify_audit()


# ---------------------------------------------------------------- validation & benchmark
@router.get("/sessions/{sid}/validation")
@locked
def validation(sid: str):
    s = _session(sid)
    _require_plan(s)
    with registry.lock(sid):
        return s.fresh_validation()


class BenchBody(BaseModel):
    sample_rows: int = Field(2000, ge=100, le=20000)
    error_rate: float = Field(0.05, gt=0, le=0.3)
    seed: int = 42


@router.get("/sessions/{sid}/benchmark")
@locked
def last_benchmark(sid: str):
    return _session(sid).benchmark_result


@router.post("/sessions/{sid}/benchmark")
@locked
def benchmark(sid: str, body: BenchBody | None = None):
    s = _session(sid)
    _require_scan(s)
    b = body or BenchBody()
    with registry.lock(sid):
        r = s.run_benchmark(sample_rows=b.sample_rows, error_rate=b.error_rate, seed=b.seed)
        registry.save(s)
        return r


# ---------------------------------------------------------------- privacy
@router.get("/sessions/{sid}/privacy")
@locked
def privacy(sid: str):
    s = _session(sid)
    _require_scan(s)
    return s.privacy_status()


class MaskBody(BaseModel):
    column: str
    method: Literal["partial", "redact", "hash", "drop"]
    table: str | None = None
    pii_type: str | None = None


@router.post("/sessions/{sid}/privacy/mask")
@locked
def mask(sid: str, body: MaskBody):
    s = _session(sid)
    _require_scan(s)
    with registry.lock(sid):
        k = s.mask_column(body.column, body.method, body.table, body.pii_type)
        registry.save(s)
        return {"checkpoint": k.to_dict(), "affected": len(k.change_ids), "findings": s.privacy_status()}


# ---------------------------------------------------------------- chat & LLM
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)


@router.post("/sessions/{sid}/chat")
@locked
def chat(sid: str, body: ChatBody):
    s = _session(sid)
    _require_plan(s)
    with registry.lock(sid):
        return answer(s, body.message, [h.model_dump() for h in body.history])


@router.get("/llm/status")
def llm_status(ping: bool = False):
    llm = get_llm()
    if ping and llm.enabled:
        try:
            llm.text("Reply with OK.")
        except Exception:
            pass
    return llm.status()


# ---------------------------------------------------------------- export
EXPORT_KINDS = {
    "cleaned_csv": ("cleaned_data.csv", "text/csv"),
    "highlighted_xlsx": ("cleaned_highlighted.xlsx",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "report_html": ("quality_report.html", "text/html"),
    "change_log_csv": ("change_log.csv", "text/csv"),
    "privacy_csv": ("privacy_report.csv", "text/csv"),
    "recipe_json": ("cleaning_recipe.json", "application/json"),
}


def _export_dir(sid: str) -> Path:
    d = Path(tempfile.gettempdir()) / "datafix_exports" / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/sessions/{sid}/export/zip")
@locked
def export_zip(sid: str):
    s = _session(sid)
    _require_plan(s)
    with registry.lock(sid):
        files = export_bundle(s, _export_dir(sid))
    return FileResponse(files["zip"], media_type="application/zip", filename="datafix_output.zip")


@router.get("/sessions/{sid}/export/{kind}")
@locked
def export_one(sid: str, kind: str, inline: bool = False):
    if kind not in EXPORT_KINDS:
        raise KeyError(kind)
    s = _session(sid)
    _require_plan(s)
    name, media = EXPORT_KINDS[kind]
    path = _export_dir(sid) / name
    with registry.lock(sid):
        if kind == "cleaned_csv":
            s.cleaned(s.main).to_csv(path, index=False)
        elif kind == "highlighted_xlsx":
            write_highlighted_xlsx(s, path)
        elif kind == "report_html":
            write_report(s, path)
        elif kind == "change_log_csv":
            s.change_log().to_csv(path, index=False)
        elif kind == "privacy_csv":
            privacy_report(s).to_csv(path, index=False)
        else:
            import json
            path.write_text(json.dumps(build_recipe(s), indent=1, ensure_ascii=False))
    # inline=1 lets the UI show the report in an iframe instead of downloading it
    return FileResponse(path, media_type=media, filename=name, content_disposition_type="inline" if inline else "attachment")
