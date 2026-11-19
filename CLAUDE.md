# DataFix — instructions for Claude Code

Hackathon build (24–36 h, solo + Claude). Specs live in `docs/`; follow them, and update the relevant doc in the same change when reality differs.

- Scope and priorities: docs/01_FINAL_PLAN.md (Tier A before B before C; don't build anything in "Cut").
- Current phase and checklist: docs/08_EXECUTION_PHASES.md.
- Algorithms: docs/05_ENGINE_SPEC.md. API shapes: docs/04_API_CONTRACT.md (change the doc first, then backend and `frontend/src/api/types.ts`).

## Non-negotiable engine rules

1. `backend/datafix` never imports FastAPI or the Gemini SDK (only `datafix/llm.py` may import `google.genai`, lazily).
2. Load every column as string; never mutate `Session.original`. All edits go through `Change` records in `audit.py`.
3. Never change a cell that has no detected issue. Anomalies are flag-only.
4. The LLM never produces cell values. Chat runs only whitelisted tools from `chat_tools.py`; no `eval`/`exec`/`df.query`/`df.eval` on model output.
5. Raw rows and PII values never go to Gemini; payloads pass `llm.sanitize()`.
6. Every LLM feature has an offline fallback; the app must work with no `GEMINI_API_KEY`. Use `DATAFIX_OFFLINE=1` for tests and rehearsals: the free tier is only 20 requests/day on 2.5 Flash.
7. Randomness is seeded (default 42).

## Commands

```bash
cd backend && uv run pytest -q
cd backend && uv run python -m datafix scan ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv
cd backend && uv run python -m datafix plan ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv --rows 412
cd backend && uv run python -m datafix fix ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv --out out/ --bench
cd backend && uv run python -m datafix bench ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv
cd backend && uv run python -m datafix check out/cleaned_data.csv --min clean_rows=95
cd backend && uv run uvicorn api.main:app --reload --port 8000
cd backend && uv run python ../scripts/smoke_api.py          # every endpoint; --live spends Gemini quota (20/day on 2.5 Flash)
cd frontend && npm run dev
cd frontend && npm run build   # type-check
cd frontend && node scripts/ui_walkthrough.mjs <outdir>   # headless Chrome click-through + screenshots (needs both servers)
cd frontend && node scripts/ui_repair.mjs <outdir>         # Repair Studio + History check
cd frontend && node scripts/ui_proof.mjs <outdir>          # Validation + Diagnosis check
cd frontend && node scripts/ui_finish.mjs <outdir>         # Chat + Privacy + Export check
scripts/start_demo.sh --offline                            # production: UI + API on :8000
cd frontend && node scripts/rehearse.mjs ../out http://localhost:8000   # full demo rehearsal + backup video (PAUSE=3500 for viewing pace)
curl -s localhost:8000/api/debug/inflight                  # what the backend is busy with right now
python3 scripts/build_pin_reference.py                     # stdlib only
cd backend && uv run python ../scripts/make_demo_data.py   # needs ~/.local/bin on PATH for uv
```

## Working style

- Python 3.12 via uv. pandas is 3.x: string columns use the `str` dtype and copy-on-write is on, so never rely on chained assignment. Type hints, small modules, pytest for every detector/validator/repair.
- Prefer finishing a feature end to end over starting a new one.
- Commit after each checklist block in docs/08_EXECUTION_PHASES.md.
- Update the affected docs in the same commit as the code (spec deviations, results, commands, phase status). Measured numbers go in docs/RESULTS.md.
- Secrets only in `.env` (gitignored).
- Restart the backend by the PID that listens on :8000 (`ss -ltnp`); `pkill -f` patterns can match the shell running them. Graceful shutdown waits for in-flight requests, so escalate to `kill -9` after 5 s.
