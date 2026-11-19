import itertools
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from datafix import __version__  # noqa: E402
from datafix.llm import get_llm  # noqa: E402

from .registry import NotFound  # noqa: E402
from .routes import router  # noqa: E402


def _default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


class AppJSON(JSONResponse):
    """numpy scalars from pandas, sets and paths serialise without per-route conversions."""

    def render(self, content) -> bytes:
        return json.dumps(content, default=_default, ensure_ascii=False, allow_nan=False).encode("utf-8")


# Production settings (all optional; local dev needs none of them):
#   DATAFIX_CORS_ORIGINS       comma list of extra allowed origins, e.g. https://datafix.vercel.app
#   DATAFIX_CORS_ORIGIN_REGEX  e.g. https://datafix-.*\.vercel\.app for Vercel preview deployments
#   DATAFIX_PUBLIC=1           hide the session list and the debug endpoint (sessions are only reachable by their id)
PUBLIC = os.getenv("DATAFIX_PUBLIC", "") in ("1", "true")
ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"] + [
    o.strip().rstrip("/") for o in os.getenv("DATAFIX_CORS_ORIGINS", "").split(",") if o.strip()]

app = FastAPI(title="DataFix API", version=__version__, default_response_class=AppJSON,
              docs_url=None if PUBLIC else "/docs", redoc_url=None, openapi_url=None if PUBLIC else "/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_origin_regex=os.getenv("DATAFIX_CORS_ORIGIN_REGEX") or None,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])


log = logging.getLogger("datafix.api")
INFLIGHT: dict[int, dict] = {}
_ids = itertools.count()
SLOW_S = 5.0


@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Every request is visible while it runs (GET /api/debug/inflight) and slow ones are logged."""
    rid = next(_ids)
    INFLIGHT[rid] = {"method": request.method, "path": request.url.path + (f"?{request.url.query}" if request.url.query else ""),
                     "started": time.time()}
    try:
        return await call_next(request)
    finally:
        info = INFLIGHT.pop(rid, None)
        if info and (d := time.time() - info["started"]) > SLOW_S:
            log.warning("slow request %.1fs %s %s", d, info["method"], info["path"])


@app.get("/api/debug/inflight")
def inflight() -> list[dict]:
    if PUBLIC:
        raise NotFound("debug endpoints are off in public mode")
    now = time.time()
    return sorted(({"method": i["method"], "path": i["path"], "running_s": round(now - i["started"], 1)}
                   for i in list(INFLIGHT.values()) if i["path"] != "/api/debug/inflight"), key=lambda x: -x["running_s"])


def _error(status: int, code: str, message: str) -> AppJSON:
    return AppJSON({"error": {"code": code, "message": message}}, status_code=status)


@app.exception_handler(NotFound)
async def _not_found(_: Request, e: NotFound):
    return _error(404, "NOT_FOUND", f"not found: {e.args[0]}")


@app.exception_handler(KeyError)
async def _key(_: Request, e: KeyError):
    return _error(404, "NOT_FOUND", f"not found: {e.args[0] if e.args else ''}")


@app.exception_handler(ValueError)
async def _value(_: Request, e: ValueError):
    return _error(409, "INVALID_STATE", str(e))


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, e: RequestValidationError):
    return _error(422, "BAD_REQUEST", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "llm": get_llm().status()["provider"],
            "offline_forced": os.getenv("DATAFIX_OFFLINE", "") in ("1", "true"), "public": PUBLIC}


app.include_router(router)

# Serve the built frontend (frontend/dist) from the same process: one command, one port for the demo.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return _error(404, "NOT_FOUND", f"no API route /{path}")
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")  # client-side routes like /s/<id>/repair
