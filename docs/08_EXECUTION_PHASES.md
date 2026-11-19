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

## Prompt plan (how the build is driven)

About 10 prompts. Each prompt runs to its exit criterion, updates the docs it touches, commits, and stops for a check.

| Phase | Prompts | Why | Status |
|---|---|---|---|
| 0 Setup | 1 | Tools, repo, demo data, PIN reference | ✅ done |
| 1 Detection | 1 | Clear spec, everything testable from the command line | ✅ done |
| 2 Repair | 2 | **2A:** confidence, tiers and all repairs; stop at row 412 and the row-1043 refusal. **2B:** change log, checkpoints and undo, CLI `fix` | ✅ done |
| 3 Proof | 1 | Ends with benchmark numbers for you to check | ✅ done |
| 4 API | 1 | Mechanical; a smoke test checks every endpoint | ✅ done |
| 5 Core UI | 2 | You need to see it. **5A:** layout, Upload and Overview. **5B:** Repair Studio and History | ✅ done |
| 6 Standout UI | 2 | **6A:** Validation and Diagnosis. **6B:** Chat, Privacy and Export | ✅ 6A · 6B next |
| 7 Freeze | 1–2 | Mostly you rehearsing; Claude fixes what breaks | |
| Stretch | — | Real-world upgrades (generic clusters, learned format/date rules, bulk review by pattern, public dirty benchmarks) if time is left | |

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
- [x] `audit.py` hash chain + verify; `session.py` replay, undo cell/batch, restore checkpoint.
- [x] CLI `fix`.
- [x] Tests: row 412 → `400001` in review/auto; conflicting-phone customer refused; never changes a clean cell (property test on `customers_clean.csv` → 0 proposals).

24h cut: PIN-from-address only via learned rules (email recovery was built).

**Phase 2A result (2026-11-19):** 38 tests pass. Demo: 1,700 proposals (auto 1,260 · review 281 · refused 149 · flag 10). Auto tier: 1,259 correct, 0 wrong, 0 valid cells touched, 75% of injected errors fixed. Auto + review: 1,461 correct, 0 wrong, 51 age estimates, 90% coverage. Every refusal is justified (age groups too spread out, no linked record, conflicting phones). Planning 0.8 s after scan. Code lives in `repair/` as text, category, pin, contact, impute, rows (not the file names listed above). Remaining for 2B: audit hash chain, session replay / undo / checkpoints, CLI `fix`.

**Phase 2B result (2026-11-19):** 49 tests pass. `datafix fix` on the demo: 1,260 auto changes in 6 checkpoints, row states 8,629 unchanged · 1,046 repaired · 405 needs review, 1,260-entry audit chain valid, 11 s end to end (scan ≈ 9 s). Tests cover: original never mutated, cached state = full replay, undo at cell / batch / restore-to-original and forward again, atomic merge undo incl. order re-pointing, accept / reject / custom value, tamper detection naming the edited entry, no change ever lands on a cell without a detected issue, save/load.

## Phase 3 — Prove (H10.5–H13.5)

- [x] `validate.py` do-no-harm checks (all 8).
- [x] Quality **dimension** scores (completeness, validity, consistency, uniqueness) next to the overall score. The overall score only moves 97.6 → 99.1 on the demo because errors are diluted over 194k cells; dimension scores show the change clearly.
- [x] `benchmark.py` inject → run → score; CLI `bench`. **Tune thresholds** so false repair rate < 0.5%; write the numbers into `docs/RESULTS.md`.
- [x] `diagnose.py` lift analysis + pattern causes.
- [x] `privacy.py` scan + mask.
- [x] `export.py`: cleaned CSV with `_datafix_status`, highlighted XLSX with comments, change_log.csv, privacy_report.csv, recipe.json, report.html (Jinja).
- [x] CLI `check` (quality gate) — 15 minutes, do it.

24h cut taken: recipe replay (`apply`) only. Calibration data was cheap and is included.

**Phase 3 result (2026-11-19):** 58 tests pass. Benchmark on 3 seeds: detection F1 0.991–0.997, repair precision 100%, false repair rate 0.000%, coverage 78–85%. Do-no-harm 8/8 after auto-fix and after masking. Clean rows 84.7% → 96.1%. Root cause finds the B07, branch_upload and partner_api stories. Privacy finds all 50 planted identifiers. Export: 7 files + ZIP in 3.3 s. `datafix check` exits 1 on the dirty file and 0 on the cleaned one. Bugs fixed on the way: free-text blanks flagged as missing (benchmark precision 20% → 100%), brittle top-5 distribution check, noise columns in root cause, the demo generator's wrong Verhoeff inverse table (13 of 25 planted Aadhaar numbers were invalid; generator now reads cached API data so the regenerated demo differs only in those 13 lines). Numbers: [RESULTS.md](RESULTS.md).

**Checkpoint H13.5: the whole product works from the CLI.** If the UI later breaks, a CLI + HTML report demo is still possible.

## Phase 4 — API (H13.5–H15.5)

- [x] `api/main.py`, `registry.py` (memory + pickle), routes per [04_API_CONTRACT.md](04_API_CONTRACT.md).
- [x] CORS for `localhost:5173`.
- [x] `llm.py` Gemini wrapper + fallbacks; `chat_tools.py`; `/chat`.
- [x] `scripts/smoke_api.py` hits every endpoint on the demo session.
- [x] Generate `frontend/src/api/types.ts` from the contract.

**Phase 4 result (2026-11-19):** 63 tests pass; `scripts/smoke_api.py` drives 46 endpoint calls through upload → scan → plan → auto → review → undo/restore → privacy → chat → validation → benchmark → export, offline and `--live`. Added beyond the contract: bulk review by pattern (`/proposals/groups`), evidence explanations, bulk undo, session list (see 04 "As built"). Live Gemini answers all 5 demo questions correctly from tool results. Found and handled the free-tier limit of 20 requests/day for 2.5 Flash (model fallback chain, quota-aware cooldown, thinking off). Real server + Vite proxy verified.

## Sleep (H15.5–H19.5)

Non-negotiable. A tired demo loses more points than a missing feature.

## Phase 5 — UI core (H19.5–H25)

Order: AppShell + header → Upload (with demo button) → Overview (KPIs, warnings, heatmap, plan/apply CTA) → Repair Studio (queue, evidence card, candidates, accept/reject, diff grid) → History (timeline, restore, change log).

Exit: the demo steps 1–8 in 09 work in the browser.

24h cut: heatmap becomes a simple per-column bar chart; diff grid shows current view only with coloured cells.

**Phase 5A result (2026-11-19):** App shell, Upload (file + linked table + demo), column-type setup with overrides and scan progress, Overview (gauge 84.7% → 96.1% after auto-fix, KPI tiles, plan/apply with Undo toast, dimension bars, smart warnings, root-cause teaser, clickable heatmap, rows drawer with PII masking). Verified in headless Chrome at 1440×900 and 1366×768, light and dark, no console errors; demo → applied fixes in ≈ 16 s of clicking. Backend additions: `dimensions`, `dimensions_now`, tier / pending counts and `pii_columns` on the session summary; warning severity reworked.

**Phase 5B result (2026-11-19):** Repair Studio (review queue + evidence cards + top-3 options + refusal banners + merge view + keyboard review + bulk review by pattern + data view) and History (checkpoint timeline with restore / undo batch, audit badge, filterable change log with per-entry undo). Verified headlessly with `ui_repair.mjs`: every step passes, no console errors, audit chain valid after 4,081 log entries. Backend: `sort=-confidence` for proposals, bulk review returns `change_ids` (precise Undo).

## Phase 6 — UI standouts (H25–H29)

Order: Validation + benchmark → Diagnosis (causes + learned rules) → Chat drawer → Privacy → Export.

24h cut: Privacy page becomes a section on Overview; chat uses offline router only if Gemini integration is fighting you.

**Phase 6A result (2026-11-19):** Validation page (8/8 checks, clean rows 84.7% → 96.1%, benchmark run from the browser: F1 0.991, repair precision 100%, false repair rate 0.000%, calibration chart) and Diagnosis page (5 source causes with per-group charts, 8 mechanism causes, learned-rules table, rows drawers). Verified with `frontend/scripts/ui_proof.mjs`, no console errors. Also added: `GET /benchmark`, culprit-first group charts, `times_elsewhere` so badges and sentences agree, **in-flight request tracking** (`GET /api/debug/inflight` + "slow request" log lines > 5 s) after a worker thread was found spinning at 100% CPU during testing (cause not reproduced; the tracker will name it if it recurs), and **debounced background session saves** (a review click no longer waits ≈ 0.6 s for the pickle).

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
