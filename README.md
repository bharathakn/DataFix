# DataFix — Autonomous Data Quality & Repair Engine

InnovEdge Hackathon 2026 · Problem Statement 01 · Data Science & Data Engineering

> Other tools clean data. DataFix tells you **why** it was dirty, repairs it using the data's own logic and trusted references, **proves** it didn't break anything, and keeps your private data private.

**DataFix: find it, explain it, fix it safely, prove it.**

## Planning documents

Read in order. Everything we build follows these docs.

| # | File | What it covers |
|---|------|----------------|
| 01 | [docs/01_FINAL_PLAN.md](docs/01_FINAL_PLAN.md) | Final scope, key decisions, what is in and out, definition of done |
| 02 | [docs/02_RESEARCH_ADDITIONS.md](docs/02_RESEARCH_ADDITIONS.md) | Review of the original report: gaps found, additions that win, things cut |
| 03 | [docs/03_ARCHITECTURE.md](docs/03_ARCHITECTURE.md) | Stack, repo layout, data models, session/checkpoint design |
| 04 | [docs/04_API_CONTRACT.md](docs/04_API_CONTRACT.md) | Every REST endpoint with request/response shapes |
| 05 | [docs/05_ENGINE_SPEC.md](docs/05_ENGINE_SPEC.md) | Detectors, repairs, confidence, validation, root cause, benchmark |
| 06 | [docs/06_AI_PRIVACY_SPEC.md](docs/06_AI_PRIVACY_SPEC.md) | Privacy shield, Gemini usage, safe chatbot design |
| 07 | [docs/07_FRONTEND_SPEC.md](docs/07_FRONTEND_SPEC.md) | Pages, components, layout, UX rules |
| 08 | [docs/08_EXECUTION_PHASES.md](docs/08_EXECUTION_PHASES.md) | Hour-by-hour build phases with checklists and exit criteria |
| 09 | [docs/09_DEMO_AND_PITCH.md](docs/09_DEMO_AND_PITCH.md) | Demo dataset, 5-minute demo script, pitch, judge Q&A |
| 10 | [docs/10_REQUIREMENTS.md](docs/10_REQUIREMENTS.md) | APIs, datasets and software, with install status |
| — | [docs/RESULTS.md](docs/RESULTS.md) | Measured benchmark, validation and timing numbers (use these on slides) |

[CLAUDE.md](CLAUDE.md) holds the rules Claude Code follows while building.

## Quick start

Requires `uv` and Node 20+ (see [docs/10_REQUIREMENTS.md](docs/10_REQUIREMENTS.md)). Copy `.env.example` to `.env` and add `GEMINI_API_KEY` (optional).

```bash
# reference + demo data (already generated; rerun any time)
python3 scripts/build_pin_reference.py
cd backend && uv run python ../scripts/make_demo_data.py && cd ..
# backend
cd backend && uv sync && uv run uvicorn api.main:app --reload --port 8000   # http://localhost:8000/api/health
# frontend
cd frontend && npm install && npm run dev                                     # http://localhost:5173 (proxies /api)
# engine only (CLI)
cd backend
uv run python -m datafix scan ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv   # detect
uv run python -m datafix plan ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv --rows 412,1043  # proposals + evidence
uv run python -m datafix fix  ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv --out out/ --mask notes:partial --bench
    # -> out/datafix_output.zip: cleaned_data.csv, cleaned_highlighted.xlsx, quality_report.html,
    #    change_log.csv, privacy_report.csv, cleaning_recipe.json (exit 2 if a do-no-harm check fails)
uv run python -m datafix bench ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv   # self-test benchmark
uv run python -m datafix check out/cleaned_data.csv --min clean_rows=95                           # quality gate (exit 1 = fail)
```
