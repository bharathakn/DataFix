# 01 · Final Plan

## 1. Constraints we are planning for

| Constraint | Value | Consequence |
|---|---|---|
| Build window | 24–36 hours | Only a demo spine plus 3–4 standout features ship. Everything else is cut or faked honestly ("roadmap"). |
| Team | Solo + Claude Code | One codebase, strict API contract, engine usable from CLI before any UI exists. |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui | Polished demo; generated quickly with Claude. |
| Backend | Python 3.12, FastAPI, pandas, RapidFuzz, scikit-learn | Engine is a plain Python package (`datafix`), API is a thin wrapper. |
| LLM | Gemini (via `google-genai` SDK) | Explanations, chat, plain-English rules only. **Never sets a cell value.** App fully works with no key. |
| Hosting | Run locally on the laptop; recorded backup video | No deploy time spent. Optional `cloudflared`/`ngrok` tunnel if judges want a link. |

## 2. Pitch (unchanged, it's good)

> Other tools clean data. DataFix tells you why it was dirty, repairs it using the data's own logic and trusted references, proves it didn't break anything, and keeps your private data private.

The demo's emotional peak: **DataFix refusing a repair because it lacks evidence**, then the **self-test benchmark** proving the false repair rate is ~0%.

## 3. Judging criteria → what proves it

The problem statement lists four things a strong solution shows. Every feature we build must map to one of these.

| Judging criterion | What we show on screen |
|---|---|
| Accuracy & consistency of detection | Live **self-test benchmark**: precision / recall / F1 per error type, run in front of judges in < 10 s |
| Safe repairs, minimal unintended changes | **Do-no-harm panel**: valid cells changed = 0, schema unchanged, distributions stable, no new errors, idempotence check. **Refusals** shown with reasons. |
| Explainability & confidence scoring | Every repair has an **evidence card** (signals, sources, confidence, tier). Top-3 candidates for uncertain cells. Tamper-evident audit log. |
| Scalability, usability, reproducibility | 100k-row timing shown in report; one-click demo; **cleaning recipe** replay + `datafix` CLI quality gate; seeded, deterministic engine |

## 4. Final scope

### Tier A — the demo spine (must work end to end by hour 15)

1. Upload CSV / Excel / JSON (+ optional linked `orders` file). One-click "Load demo dataset".
2. Automatic column-type detection (email, phone, PIN, date, age, money, PAN, GSTIN, Aadhaar, id, category, free text).
3. Detection: missing, **disguised missing** (`N/A`, `-`, `9999999999`, `1900-01-01`, `test@test.com`), duplicates (exact + fuzzy), invalid formats, Indian validators, inconsistent representations, **auto-discovered dependency violations** (PIN→City, City→State), cross-field rules, anomalies (flag only).
4. Repair engine with ranked candidates and multi-signal confidence: format normalisation, standardisation to dominant form, spelling fix, PIN ↔ address, PIN digit recovery, phone recovery from linked table, group-median age imputation (estimate), dedupe with merge rules.
5. Confidence tiers: ≥ 0.95 auto · 0.70–0.95 review queue · < 0.70 flag only. Explicit **refusals** with reason.
6. Audit log (one record per changed cell, hash-chained) + checkpoint timeline with undo at cell / batch / all levels.
7. Do-no-harm validation + quality score before → after.
8. Export ZIP: cleaned data, highlighted Excel, HTML quality report, change log, privacy report, recipe.

### Tier B — the standouts (hours 15–29)

9. **Self-test benchmark** (button in UI).
10. **Root-cause diagnosis** (source / batch / date lift analysis + pattern causes like Excel scientific notation and encoding damage).
11. **Privacy shield** (Aadhaar Verhoeff, PAN, GSTIN checksum, IFSC, phone, email, card Luhn, PII in free text) + one-click mask / hash / redact / drop.
12. **Dataset chatbot** on Gemini with whitelisted tool calls only.
13. Error heatmap, top-3 candidates, before/after diff grid.

### Tier C — stretch (only if ahead of schedule)

14. Plain-English rules → validation rule via Gemini, confirmed by user.
15. Recipe replay on a new file (`datafix apply recipe.json next_month.csv`).
16. Quality gate CLI: `datafix check sales.csv --min-score 90` (exit code 1 on fail). Very cheap once the engine exists — likely makes it.
17. PDF report (WeasyPrint). HTML report is primary.

### Cut (mention as roadmap in the pitch, don't build)

Drift tracking across uploads, downstream impact preview, full multi-table relationship graph (we only do the customers ↔ orders link), Polars backend, PostgreSQL, Docker, Vercel/Render deploy, multi-user approvals, auth.

## 5. Key decisions

| Decision | Choice | Why |
|---|---|---|
| Engine vs API | `datafix` package has zero FastAPI imports | Testable from CLI, reusable for quality gate, survives UI failure |
| Load dtype | Read every column as string (`dtype=str, keep_default_na=False`) | Never silently change a value on load (leading zeros, `NA` strings, big numbers) |
| Original file | Read-only; current state = original + replay of applied changes | Undo is free, original never mutated |
| Storage | In-memory session dict + pickle snapshot to `backend/.sessions/` | No DB setup time |
| Confidence | Noisy-OR over evidence signals, penalised by conflicting signals; thresholds tuned on benchmark | Explainable, calibratable, no training |
| Chatbot | Gemini function calling → whitelisted JSON operations | No arbitrary code execution (the original plan's "LLM writes pandas" is an injection risk) |
| Reference data | Bundled India Post PIN CSV (slimmed); `api.postalpincode.in` fallback, cached | Works offline at the venue |
| Report | Jinja2 HTML (print-to-PDF), WeasyPrint optional | Avoid system-library install pain |
| Inconsistent forms (Bangalore / Bengaluru) | Standardise to the column's dominant canonical form, logged as `standardize`, never counted as "valid value changed" | Problem statement lists inconsistent entries as an error class |
| Age imputation | Group **median** (not mean), only groups ≥ 5 with IQR ≤ 15; always review tier; adds `_imputed` marker | Mean is outlier-sensitive; imputation is a guess and must be visible |

## 6. Definition of done (judging day)

- [ ] Demo dataset loads in one click; full flow runs with no errors, with and without internet.
- [ ] Benchmark runs live and shows false repair rate < 0.5% and F1 ≥ 0.85 on the demo data.
- [ ] Row 412 PIN story, row 52 change explanation, and one refused repair all work exactly as in [09_DEMO_AND_PITCH.md](09_DEMO_AND_PITCH.md).
- [ ] Undo to an earlier checkpoint and forward again works.
- [ ] Export ZIP opens: cleaned CSV, highlighted XLSX, report.html, change_log.csv, privacy_report.csv, recipe.json.
- [ ] 10k rows end to end < 30 s; 100k rows timing recorded for the slide.
- [ ] Backup screen recording saved locally.
