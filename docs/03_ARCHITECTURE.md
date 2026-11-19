# 03 · Architecture

## 1. Layers

```
React (Vite, TS)  ──HTTP/JSON──▶  FastAPI (backend/api)  ──calls──▶  datafix engine (backend/datafix)
   pages, grid,                     thin routes, session                pure Python: ingest, detect,
   chat drawer                      registry, file I/O                  repair, validate, privacy, …
                                          │                                   │
                                          └──▶ Gemini (optional) ◀────────────┘ summaries only
```

Rule: **the engine never imports FastAPI or Gemini.** LLM access lives in `datafix/llm.py` behind an interface with a template fallback; the engine works with it disabled.

## 2. Final stack

| Area | Choice |
|---|---|
| Python | 3.12 via `uv` (`uv init`, `uv add …`) |
| Engine libs | pandas, numpy, rapidfuzz, scikit-learn (IsolationForest), python-dateutil, openpyxl, chardet/charset-normalizer, jinja2 |
| API | fastapi, uvicorn, python-multipart, pydantic v2 |
| LLM | google-genai; model name from env `GEMINI_MODEL` (use the current Flash model) |
| Tests | pytest |
| Frontend | React 18 + Vite + TypeScript, Tailwind, shadcn/ui, TanStack Query, TanStack Table (virtualised grid), Recharts, lucide-react, react-router |
| Config | `.env` (gitignored): `GEMINI_API_KEY`, `GEMINI_MODEL`, `DATAFIX_SESSION_DIR` |

## 3. Repository layout

```
DataFix/
├── CLAUDE.md
├── README.md
├── docs/
├── data/
│   ├── demo/                      # generated: customers_clean.csv, customers_dirty.csv, orders.csv, truth.json
│   └── reference/pincodes.csv     # slimmed India Post directory: pin,office,district,state
├── scripts/
│   ├── make_demo_data.py          # seeded generator with story rows
│   └── build_pin_reference.py     # raw data.gov.in CSV → slim pincodes.csv
├── backend/
│   ├── pyproject.toml
│   ├── datafix/
│   │   ├── __init__.py
│   │   ├── __main__.py            # CLI: scan | fix | check | apply | bench
│   │   ├── models.py              # dataclasses / pydantic models below
│   │   ├── ingest.py              # load csv/xlsx/json as strings, encoding sniff
│   │   ├── coltypes.py            # semantic column type detection
│   │   ├── profile.py             # per-column stats
│   │   ├── validators.py          # email, phone, pin, pan, gstin, aadhaar, ifsc, luhn, dates, money
│   │   ├── knowledge.py           # placeholder tokens, city aliases, GST state codes
│   │   ├── reference.py           # India Post PIN reference loader
│   │   ├── scan.py                # orchestrates coltypes + detectors + score
│   │   ├── detect/                # missing, disguised, duplicates, formats, consistency, fd, crossfield, anomalies
│   │   ├── repair/                # normalize, standardize, spelling, pin, phone, age, dedupe, fd_repair
│   │   ├── confidence.py          # signal combination + tiering
│   │   ├── planner.py             # issues → candidates → RepairProposal list
│   │   ├── session.py             # Session: original df, change list, checkpoints, current() replay
│   │   ├── audit.py               # Change records, hash chain, verify
│   │   ├── validate.py            # do-no-harm checks, quality score
│   │   ├── diagnose.py            # root-cause lift analysis + pattern causes
│   │   ├── privacy.py             # PII scan + masking
│   │   ├── benchmark.py           # inject → run → score
│   │   ├── chat_tools.py          # whitelisted operations the chatbot may call
│   │   ├── llm.py                 # Gemini wrapper + template fallback
│   │   ├── export.py              # zip: csv, xlsx highlight, report.html, logs, recipe
│   │   ├── recipe.py              # record / replay approved steps
│   │   └── templates/report.html.j2
│   ├── api/
│   │   ├── main.py                # app, CORS, routers
│   │   ├── registry.py            # session_id → Session (memory + pickle)
│   │   └── routes/                # sessions, scan, repair, history, validation, privacy, chat, export
│   └── tests/
└── frontend/
    ├── src/
    │   ├── api/                   # typed client + react-query hooks (mirrors 04_API_CONTRACT)
    │   ├── pages/                 # Upload, Overview, Diagnosis, RepairStudio, Privacy, Validation, History, Export
    │   ├── components/            # DataGrid, Heatmap, EvidenceCard, CandidatePicker, Timeline, ChatDrawer, ScoreGauge…
    │   └── lib/
    └── …
```

## 4. Core data models

All IDs are short strings (`I0001`, `P0001`, `C0001`, `K01`). `row_id` is the stable row index assigned at load (`_rid`, 0-based, never reused). Display uses the dataset's own ID column when present.

```python
class ColumnInfo:          # from coltypes + profile
    name: str
    semantic_type: str     # email|phone|pin|date|age|money|pan|gstin|aadhaar|ifsc|id|category|name|text|number|unknown
    type_confidence: float
    null_count: int; distinct: int; sample: list[str]

class Issue:
    issue_id: str
    row_id: int | None     # None for column/dataset level issues
    column: str | None
    type: str              # missing|disguised_missing|duplicate|near_duplicate|invalid_format|inconsistent|fd_violation|crossfield|anomaly|pii
    severity_weight: float
    detector: str          # e.g. "fd:pin->city"
    message: str           # template sentence
    value: str | None
    meta: dict             # detector-specific evidence

class Signal:
    name: str              # "string_similarity", "fd_majority", "reference_pin", "linked_table_match", …
    score: float           # 0..1 strength
    reliability: float     # 0..1 prior trust in this signal type
    detail: str            # human sentence: "PIN 560001 maps to Bengaluru in India Post directory"
    conflicting: bool = False

class Candidate:
    value: str
    confidence: float
    signals: list[Signal]

class RepairProposal:
    proposal_id: str
    issue_ids: list[str]
    row_id: int; column: str
    original_value: str
    candidates: list[Candidate]   # sorted, max 3
    tier: str                      # auto|review|flag|refused
    repair_class: str              # normalize|standardize|correct|impute|dedupe_merge|recover
    algorithm: str
    refusal_reason: str | None
    status: str                    # pending|applied|rejected|undone

class Change:                      # one per changed cell — the audit record
    change_id: str; checkpoint_id: str; proposal_id: str | None
    row_id: int; column: str
    original_value: str; new_value: str
    reason: str; evidence: list[str]; source: str
    confidence: float; algorithm: str
    status: str                    # applied|undone
    actor: str                     # auto|user|chat
    timestamp: str                 # ISO 8601
    prev_hash: str; hash: str      # sha256(prev_hash + canonical json of the fields above)

class Checkpoint:
    checkpoint_id: str; label: str  # "Formats normalised", "Duplicates merged", …
    change_ids: list[str]; created_at: str
    quality_score: float
```

Row deletions (dedupe) are a `Change` with `column="__row__"`, `new_value="__deleted__"`, plus `Change`s on `orders.customer_id` for remapped foreign keys.

## 5. Session and checkpoint design

- `Session.original` — DataFrame loaded once, all strings, never mutated. Fingerprint = SHA-256 of raw file bytes (stored in the report).
- `Session.changes` — append-only list of `Change`.
- `Session.current()` — `original.copy()` then replay all changes with `status == "applied"` in order. Cache the result; invalidate on any change. 10k × 20 replay is milliseconds.
- **Undo cell** — mark that `Change` `undone` (write a new audit entry `undo C0042`, the chain is never rewritten).
- **Undo batch** — mark every change in checkpoint K `undone`.
- **Restore to checkpoint K** — mark every change in checkpoints after K `undone`; "redo" re-applies them. The timeline shows the full branch.
- Linked tables (orders) live in `Session.tables: dict[str, DataFrame]`, same change mechanism with `table` field.
- Persistence: after each mutation, pickle the session to `.sessions/<id>.pkl` so a backend restart during the demo doesn't lose state.

### 5a. As built (Phase 2B, `datafix/session.py`, `datafix/audit.py`)

- **The log is append-only.** Every entry is a `Change` with `action` = `apply` | `undo` | `redo` | `reject`. Undo/redo never edit an old entry's values: they append a new entry pointing at it (`target`) and flip the old entry's derived `status`.
- **Hash chain:** `hash = sha256(prev_hash + canonical JSON of every field except status/hash)`. The chain starts from a genesis hash of the input files' SHA-256, so the log is tied to exactly those files. `verify()` names the first broken entry.
- **Current state:** the original replayed with every `apply` entry whose status is `applied`. Applying a change updates the cached table in place (no replay); undo/redo invalidates and replays (10k rows: milliseconds).
- **Checkpoints:** `K00 Original`, one per auto batch, and a rolling "Review decisions" checkpoint that collects consecutive review actions, so the timeline doesn't get one node per click. `restore(K)` makes exactly checkpoints ≤ K active and works backwards and forwards.
- **Duplicate merges are atomic:** fills on the survivor + foreign-key re-points in linked tables + the row removal share one proposal; undoing any of them undoes all.
- **Rejections are logged** (`action=reject`), so the audit trail records human decisions as well as changes.
- **Scores per checkpoint** are a fast estimate: scan issues minus resolved cells/rows. Phase 3 validation re-scans the repaired data.
- **Persistence:** `Session.save(dir)` / `Session.load(path)` pickle the whole session.

## 6. Request flow (happy path)

1. `POST /sessions` → ingest, coltypes, profile → returns `session_id` + profile.
2. `POST /scan` → detectors + privacy scan + root cause → issues, warnings, PII, heatmap, score.
3. `POST /repair/plan` → proposals with candidates and tiers.
4. `POST /repair/apply-auto` → applies tier `auto` in batches by repair class, one checkpoint per batch.
5. User reviews queue → `POST /review/{proposal_id}` accept / reject / choose candidate.
6. `GET /validation` → do-no-harm + score after.
7. `POST /benchmark` (any time).
8. `GET /export` → ZIP.

## 7. Performance budget

| Step | 10k rows target | Notes |
|---|---|---|
| Load + types + profile | < 2 s | Sample 2k values per column for type detection |
| Detection | < 6 s | Vectorised regex (`str.match`), blocking for fuzzy duplicates |
| Plan | < 8 s | RapidFuzz `process.extract` against column vocabulary, not row × row |
| Apply + validate | < 4 s | |
| Benchmark | < 15 s | Runs on a 2k-row sample by default |
