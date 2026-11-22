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
| 6 Standout UI | 2 | **6A:** Validation and Diagnosis. **6B:** Chat, Privacy and Export | ✅ done |
| 7 Freeze | 1–2 | Mostly you rehearsing; Claude fixes what breaks | ✅ engine + rehearsal done; human rehearsal + slides left |
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

**Phase 6B result (2026-11-19):** Chat side panel (suggested questions, visible tool calls, confirmable undo), Privacy page (grouped findings, per-column masking with undo, mask all high-risk), Export page (validation status, ZIP + six downloads, inline report preview). Verified with `frontend/scripts/ui_finish.mjs`: chat answers Pune / row 412 / row 1043 correctly, "Undo the city fixes" → Confirm undid 323 changes, masking notes + PAN keeps 8/8 checks, ZIP downloads, no console errors. Fixes on the way: masked values no longer count as invalid after repair (clean rows showed 37.5%), idempotence ignores open review items, report preview served inline. **Stuck-thread follow-up:** it happened while "Accept all" / "Reject" were clicked in the browser; not reproducible (279 concurrent reads during bulk accepts were clean), but the plausible cause was fixed: every session route now holds the session lock for the whole request, so no read can rebuild the table while a repair mutates it.

## Phase 7 — Freeze and rehearse (H29–H32)

- [x] Feature freeze at H29.
- [ ] Run the demo script 3× end to end with a timer. Fix only what breaks.
- [x] Test with Wi-Fi off (offline templates, cached PIN data).
- [x] Record a full backup video (OBS / screen recorder), save locally and on a USB drive.
- [x] Time 10k and 100k rows; put numbers on the slide.
- [ ] Slides (6–8) per 09 §3.
- [x] Fill README quick start; screenshots.

**Phase 7 result (2026-11-19):**
- One-command demo: `scripts/start_demo.sh [--offline] [--lan]` builds the UI and serves UI + API on :8000 (FastAPI serves `frontend/dist`, SPA deep links work).
- Automated rehearsal `frontend/scripts/rehearse.mjs` runs the 11 demo steps on the production build, asserts **no request leaves localhost** (Wi-Fi-off safe) and no console errors, and records `out/demo_backup.webm` (≈ 2 min at `PAUSE=3500`).
- Performance: 100k customers + 233k orders end to end **700 s → 150 s**; 10k demo 20.5 s (numbers in RESULTS.md). Demo generator gained `--rows` (errors scale; the 10k file is byte-identical).
- Docs: demo script rewritten click-by-click with real numbers, slide 6 / Q&A use measured results, backup plan updated.
- Left for the human: rehearse 3× with a timer, slides, copy the video to USB/phone, decide on Gemini quota (billing cap or a key from another project), Gemini live check after the quota resets (≈ 13:30 IST).

## Working with Claude Code during the build

- Start each phase with: "Implement Phase N from docs/08_EXECUTION_PHASES.md following docs/05_ENGINE_SPEC.md." Claude reads [CLAUDE.md](../CLAUDE.md) automatically.
- One module per request; ask for its tests in the same request; run them before moving on.
- Commit at the end of every checklist block (`git commit -m "phase2: pin recovery"`), so a bad change is one `git revert` away.
- When something in a spec turns out wrong, update the doc in the same commit.

**Post-Phase 7 (2026-11-19): Accept all for the review queue.** Clicking through about 3k review items one at a time was too slow, so there is now a warned "Accept all" (see 07 and 04). Server side: `Session.accept_all()` applies every pending review suggestion as one `bulk` checkpoint. Cell fixes go first, most confident first, one per cell; merges go last, skipping rows already merged away. Undoing a review suggestion now returns it to `pending` instead of hiding it as `undone`. Demo: 281 items in 0.1 s; `ui_accept_all.mjs` passes with no console errors; 64 tests pass. Tried on a user's unknown 30k-row file: 3,131 review items, preview ≈ 433 likely wrong, 0 collisions. Display fix: the UI's e-mail mask hid malformed addresses entirely (`a@@b.com` showed as `***`); it now masks only the mailbox and keeps the rest (`am***@@gmail.com`), so the typo being fixed is visible. The stored data was never masked.

**Bulk reject + privacy opt-out (2026-11-20).** Reject all (with a warning) on the Review, Patterns, Refused and Flagged tabs. It changes no cell, issues stay open, and Undo reopens the items. Privacy gets "Keep as is" per column and "Keep all unmasked", logged in the audit chain and shown in `privacy_report.csv`. Verified: 66 tests pass, `smoke_api.py` passes 47 endpoints, and `ui_accept_all.mjs` (accept 281 → undo, reject 149 refused → undo, keep/unkeep, keep all) passes with no console errors.

**Unknown-dataset performance (2026-11-20).** On a 30k-row upload with a 161k-entry log, "Download all" took about 20 min and the report preview stayed blank. Causes: a linear `_by_id` lookup made checkpoint, undo and restore calls quadratic while holding the session lock, and openpyxl comments were slow. After the fixes, the ZIP takes 27 s cold and is instant on repeat. Numbers are in RESULTS.md. New dependency: `xlsxwriter`.

**Post-Phase 7 (2026-11-20): Groq as backup LLM.** The chain is now Gemini (each model × main/backup key) → Groq (`openai/gpt-oss-120b` → `qwen/qwen3.8-27b` → `openai/gpt-oss-20b`; OpenAI-compatible HTTP via httpx) → offline templates. Groq covers narratives, explanations and chat with the same whitelisted tools and the same `sanitize()` step (06 §2a). Responses and `/llm/status` report `groq`; the header badge shows "AI: Groq (backup)". `tests/test_llm_groq.py` adds 6 mocked tests: sanitized payload, 429 cooldown, retired model skipped, Gemini→Groq fall-through, offline flag, non-whitelisted tool refused. 72 tests pass. Live check with the real key: Groq answered the chat demo question correctly (1,352 Bengaluru customers) via `count_rows` in 1.5 s.

**Post-Phase 7 (2026-11-20): fixes from the answer-key test set.** A scored run on an unseen 30k-row dataset showed 5,836 wrong fixes and large misses. Added canonical formats (phone/email/PAN/PIN/name), boolean and gender value families, state codes and job synonyms, age computed from date of birth (learned rule, new `Ages computed from date of birth` checkpoint), no `notes` copying in merges, and a meaning-based distribution check (05 §4.0, §5.2, §7.2). On the listed cells: 26,495 correct and 0 wrong (was 1,488 / 5,836); details in RESULTS.md. Demo numbers unchanged except K01 313 → 363 (1,310 auto fixes). 80 tests pass (`tests/test_canonical.py` adds 8).

**Post-Phase 7 (2026-11-20): UI redesign.** One warm theme across all pages (paper background, teal primary, clay/ochre/sage status colours, Newsreader titles, Inter text; fonts bundled locally), new sidebar shell with Column types in the nav, `PageHeader`/`Card`/`Kpi` restyled, Upload rebuilt, Overview leads with a sentence and adds a problems-by-type donut, Setup column cards, History timeline and chat header tidied (07 §0a). All UI scripts pass (walkthrough, repair, proof, finish, accept-all) and the rehearsal passes 11/11 with no external requests. Two scripts had fragile locators, now fixed: `ui_repair` clicked the bulk "Accept all 281" instead of a pattern's "Accept all" (exact match now), and `ui_proof` matched the AI pill (now scoped to `main`). The backup video in `out/` still shows the old UI until it is re-recorded.

**Post-Phase 7 (2026-11-20): deployment.** UI on Vercel (`frontend/vercel.json`, `VITE_API_URL`), API in a Docker container on Render (`Dockerfile`, `render.yaml`): the API keeps sessions in memory and on disk and takes uploads over 4.5 MB, so it cannot run as Vercel functions (docs/DEPLOY.md). Hardening for a public server: `DATAFIX_PUBLIC` hides the session list, debug endpoint and API docs; `DATAFIX_SESSION_TTL_H` deletes idle sessions; `DATAFIX_MAX_UPLOAD_MB` also covers the linked file; CORS origins from the environment. `httpx` became a runtime dependency (Groq) and unused `scikit-learn` was removed (no-dev install 360 → 180 MB). Peak memory: 225 MB demo, 555 MB for 30k + 81k rows. Verified across two origins: rehearsal 11/11; 83 tests pass.

**Post-Phase 7 (2026-11-20): 55-row answer key.** `data/testsets/df55` (input + expected action per row) matched 44 of 55 rows at first (DF009, 018, 021, 024, 032, 034, 035, 042, 044, 052, 055 wrong), with more wrong values underneath: wrong column types for `age` (`24.0`) and `customer_status` (header hint "customer"), a false outlier at 4,500, missed `2025/07/03`, `MUMBAI`, `New Delhi`, `A`, `Actve`, `Customer`, a wrong e-mail guess, and exact duplicates merged without review. Generic rules added (05 §4.2); `tests/test_expected_df55.py` now passes 55/55 by behaviour (untouched / auto / review). Demo detection unchanged; the 120 exact duplicates (new IDs) moved from auto to review, so auto-fix is 1,189 changes in 5 checkpoints and clean rows 84.7% → 94.95% (RESULTS §3). 101 tests pass.

**Post-Phase 7 (2026-11-22): 1,000-row app demo.** The hosted demo was slow on the free Render instance, so **Load demo dataset** now opens `data/demo_small` (1,020 customers + 2,318 orders, 189 planted errors; `DATAFIX_DEMO_DIR` switches back). The generator places story rows inside small files (52, 412, 777 unchanged; conflicting phones 643, ages 201/202, outlier 300) and keeps the root-cause stories above the diagnosis threshold; the 10k demo is byte-identical, so engine tests are unchanged. Updated: Dockerfile (ships only the small demo), `render.yaml` auto-deploy, Upload text, chat suggestion (row 643), `smoke_api.py` and the UI scripts (rows/IDs; drawer table locator scoped with `data-testid="drawer"` after a race showed up at the faster speed). Results: whole flow 4.7 s, rehearsal 10.6 s (was 31 s), 8/8 checks, 101 tests pass (RESULTS.md).
