# 08 · Execution Phases

Solo build with Claude Code, ~30 working hours inside a 36-hour window (includes a 4-hour sleep). Hours are from kickoff (H0). **Engine first, UI second, polish last.** At the end of every phase the project must run.

If the window is only 24 hours, apply the **24h cut** noted in each phase.

## Overview

| Phase | Hours | Goal | Exit criterion |
|---|---|---|---|
| 0 Setup | H0–H1.5 | Repo, envs, demo data, PIN reference | `make_demo_data.py` writes the demo files; both servers start |
| 1 Detect | H1.5–H5.5 | Ingest, column types, all detectors, score | `python -m datafix scan` prints correct issues on demo data |
| 2 Repair | H5.5–H10.5 | Candidates, confidence, tiers, audit, checkpoints | `python -m datafix fix` writes cleaned CSV + change log; row 412 works |
| 3 Prove | H10.5–H13.5 | Do-no-harm, benchmark, root cause, privacy scan + mask | `bench` prints metrics; diagnosis finds the B07 story |
| 4 API | H13.5–H15.5 | FastAPI routes per contract | All endpoints return contract shapes (smoke test script) |
| — Sleep | H15.5–H19.5 | | |
| 5 UI core | H19.5–H25 | Upload, Overview, Repair Studio, History | Full demo flow clickable in the browser |
| 6 UI standouts | H25–H29 | Validation/benchmark, Diagnosis, Privacy, Chat, Export | Every demo step in 09 works |
| 7 Freeze | H29–H32 | Polish, rehearse ×3, record backup video, slides | Feature freeze at H29. Only bug fixes after |
| Buffer | H32–H36 | Slippage | |

---

## Phase 0 — Setup (H0–H1.5)

- [x] `git init` (no commits yet); `.gitignore` (`.env`, `.venv`, `node_modules`, `.sessions`, `data/demo/*.csv` optional).
- [x] Backend: `uv init backend --python 3.12`; `uv add pandas numpy rapidfuzz scikit-learn python-dateutil openpyxl charset-normalizer jinja2 fastapi uvicorn python-multipart pydantic google-genai python-dotenv`; `uv add --dev pytest`.
- [x] Frontend: `npm create vite@latest frontend -- --template react-ts`; Tailwind; `npx shadcn@latest init`; add `@tanstack/react-query @tanstack/react-table @tanstack/react-virtual recharts react-router-dom lucide-react`.
- [x] PIN reference: download the All-India Pincode directory CSV from data.gov.in → `scripts/build_pin_reference.py` → `data/reference/pincodes.csv` (`pin,office,district,state`, deduped to pin+district+state). **If download fails**, generate a reference from the demo generator's city table for the demo PINs and note it.
- [x] `scripts/make_demo_data.py` per [09_DEMO_AND_PITCH.md](09_DEMO_AND_PITCH.md) §1 — writes `customers_clean.csv`, `customers_dirty.csv`, `orders.csv`, `truth.json`.
- [x] `.env.example` with `GEMINI_API_KEY=`, `GEMINI_MODEL=`.
- [x] Verify Gemini key with a 5-line script (`gemini-2.5-flash`, v1beta, function calling OK).

## Phase 1 — Detect (H1.5–H5.5)

- [x] `models.py` (dataclasses from 03 §4).
- [x] `ingest.py` (strings only, `_rid`, encoding sniff, xlsx, json).
- [x] `validators/` with unit tests: Verhoeff, Luhn, GSTIN checksum, PAN, PIN, phone, email, dates, money parsing.
- [x] `coltypes.py` + test that a renamed `col_7` PIN column is detected.
- [x] `detect/`: missing, disguised, duplicates (exact + blocked fuzzy), formats, consistency (aliases, case, mixed formats), FD discovery, crossfield, anomalies.
- [x] `validate.quality_score()`.
- [x] CLI `scan`.
- [x] Test: counts per type on demo data roughly match `truth.json`.

24h cut taken: multivariate IsolationForest and column-shift skipped (robust z only).

**Result (2026-11-19):** 33 tests pass. Demo detection vs truth.json: precision 1.000, recall 0.990 (every error type ≥ 0.9 except US dates with day ≤ 12, 0.66, undetectable per cell). Clean file: 0 false flags, score 100. Scan time: customers 10.2k rows 4.9 s, orders 23k rows 4.1 s. Scores are on our own synthetic data, so expect lower on real files.

## Phase 2 — Repair (H5.5–H10.5)

- [x] `confidence.py` noisy-OR + tiers.
- [x] `repair/normalize.py` (phone, dates, money, whitespace, sci-notation, encoding).
- [x] `repair/standardize.py`, `repair/spelling.py` (top-3 with RapidFuzz).
- [x] `repair/fd_repair.py`.
- [x] `repair/pin.py` (reference lookup, digit recovery §5.5), `repair/phone.py` (linked table), `repair/age.py` (group median), `repair/dedupe.py` (survivorship + FK remap).
- [x] `planner.py` → proposals with refusals.
- [ ] `audit.py` hash chain + verify; `session.py` replay, undo cell/batch, restore checkpoint.
- [ ] CLI `fix`.
- [x] Tests: row 412 → `400001` in review/auto; conflicting-phone customer refused; never changes a clean cell (property test on `customers_clean.csv` → 0 proposals).

24h cut: PIN-from-address only via learned rules (email recovery was built).

**Phase 2A result (2026-11-19):** 38 tests pass. Demo: 1,700 proposals (auto 1,260 · review 281 · refused 149 · flag 10). Auto tier: 1,259 correct, 0 wrong, 0 valid cells touched, 75% of injected errors fixed. Auto + review: 1,461 correct, 0 wrong, 51 age estimates, 90% coverage. Every refusal is justified (age groups too spread out, no linked record, conflicting phones). Planning 0.8 s after scan. Code lives in `repair/` as text, category, pin, contact, impute, rows (not the file names listed above). Remaining for 2B: audit hash chain, session replay / undo / checkpoints, CLI `fix`.

## Phase 3 — Prove (H10.5–H13.5)

- [ ] `validate.py` do-no-harm checks (all 8).
- [ ] `benchmark.py` inject → run → score; CLI `bench`. **Tune thresholds** so false repair rate < 0.5%; write the numbers into `docs/RESULTS.md`.
- [ ] `diagnose.py` lift analysis + pattern causes.
- [ ] `privacy.py` scan + mask.
- [ ] `export.py`: cleaned CSV with `_datafix_status`, highlighted XLSX with comments, change_log.csv, privacy_report.csv, recipe.json, report.html (Jinja).
- [ ] CLI `check` (quality gate) — 15 minutes, do it.

24h cut: calibration chart data, recipe replay (`apply`).

**Checkpoint H13.5: the whole product works from the CLI.** If the UI later breaks, a CLI + HTML report demo is still possible.

## Phase 4 — API (H13.5–H15.5)

- [ ] `api/main.py`, `registry.py` (memory + pickle), routes per [04_API_CONTRACT.md](04_API_CONTRACT.md).
- [ ] CORS for `localhost:5173`.
- [ ] `llm.py` Gemini wrapper + fallbacks; `chat_tools.py`; `/chat`.
- [ ] `scripts/smoke_api.py` hits every endpoint on the demo session.
- [ ] Generate `frontend/src/api/types.ts` from the contract.

## Sleep (H15.5–H19.5)

Non-negotiable. A tired demo loses more points than a missing feature.

## Phase 5 — UI core (H19.5–H25)

Order: AppShell + header → Upload (with demo button) → Overview (KPIs, warnings, heatmap, plan/apply CTA) → Repair Studio (queue, evidence card, candidates, accept/reject, diff grid) → History (timeline, restore, change log).

Exit: the demo steps 1–8 in 09 work in the browser.

24h cut: heatmap becomes a simple per-column bar chart; diff grid shows current view only with coloured cells.

## Phase 6 — UI standouts (H25–H29)

Order: Validation + benchmark → Diagnosis (causes + learned rules) → Chat drawer → Privacy → Export.

24h cut: Privacy page becomes a section on Overview; chat uses offline router only if Gemini integration is fighting you.

## Phase 7 — Freeze and rehearse (H29–H32)

- [ ] Feature freeze at H29.
- [ ] Run the demo script 3× end to end with a timer. Fix only what breaks.
- [ ] Test with Wi-Fi off (offline templates, cached PIN data).
- [ ] Record a full backup video (OBS / screen recorder), save locally and on a USB drive.
- [ ] Time 10k and 100k rows; put numbers on the slide.
- [ ] Slides (6–8) per 09 §3.
- [ ] Fill README quick start; screenshots.

## Working with Claude Code during the build

- Start each phase with: "Implement Phase N from docs/08_EXECUTION_PHASES.md following docs/05_ENGINE_SPEC.md." Claude reads [CLAUDE.md](../CLAUDE.md) automatically.
- One module per request; ask for its tests in the same request; run them before moving on.
- Commit at the end of every checklist block (`git commit -m "phase2: pin recovery"`), so a bad change is one `git revert` away.
- When something in a spec turns out wrong, update the doc in the same commit.
