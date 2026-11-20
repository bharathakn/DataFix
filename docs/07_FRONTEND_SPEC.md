# 07 · Frontend Specification

React 19 + Vite + TypeScript + Tailwind v4. TanStack Query for server state, lucide-react icons, react-router.

## 0. As built (Phase 5A)

- **No shadcn/ui.** Its CLI setup is interactive and fiddly with Tailwind v4; we only need ~10 primitives, so they're hand-written in `src/components/ui.tsx` (Button, Card, Badge, Kpi, Skeleton, Spinner, ErrorNote, EmptyState, Drawer, Legend). Recharts / TanStack Table are not needed yet: the gauge, dimension bars and heatmap are plain SVG/CSS (`components/viz.tsx`), the grid is a paged table (`components/DataGrid.tsx`, 50 rows/page, sticky header).
- **Routes:** `/` Upload · `/s/:sid/setup` column types (override before scanning; animated scan progress) · `/s/:sid` Overview · other pages are placeholders until 5B/6A/6B. Overview redirects to setup while the session is unscanned.
- **API layer:** `src/api/client.ts` (typed fetch, `{error:{code,message}}` → `ApiError`), `src/api/hooks.ts` (React Query; every key starts with the session id, so one invalidation refreshes a page after any mutation).
- **Personal data:** column samples and the data grid mask phone / email / Aadhaar / PAN / GSTIN / IFSC / free-text digits by default (`maskSample`); the grid has a "Show personal data" toggle for reviewers.
- **Overview:** clean-rows gauge (before → after, using the cheap `dimensions_now` from the session summary; Validation does the full re-check) · 8 KPI tiles (click → rows drawer) · next-step card (Plan → Apply N fixes with an Undo toast → Repair Studio / Validation) · dimension bars before/after · smart warnings (severity: duplicates, placeholders, rule breaks and widespread blanks high; formatting noise low) with "Show rows" · root-cause teaser · heatmap (click a cell → rows of that block, column first).
- **Grid:** the column the user came for is moved first; cell colours from `.cell-*` classes in `index.css`; hovering a repaired cell shows its before-value.
- **Theme:** light default (projectors), dark toggle stored in localStorage and applied before first paint.
- **Repair Studio (5B):** tabs Review · Patterns · Refused · Flagged · Applied with counts; column filter (incl. "Duplicate rows"); review queue sorted most-confident-first by default (toggle). Evidence card: record line, original → chosen value, refusal / flag banner, the whole row as a grid with the target cell outlined, top-3 options as radio cards with confidence bars, evidence list (✓ supporting, ✗ conflicting, ℹ explanatory), "Explain in plain English" on demand (saves Gemini quota), Accept / Reject / custom value, Undo toast; applied items get "Undo this repair". Duplicate merges show duplicate and survivor rows side by side with what the merge fills and re-points. Keys: A accept, R reject, J/K next/previous, 1–3 choose an option (buttons carry `data-action`). Patterns tab = bulk review by pattern with Accept all / Reject all and Undo. **Accept all (review queue):** a red "Accept all N" button on the Review tab (respects the column filter) opens a warning dialog: ≈ likely-wrong fixes (Σ 1 − confidence), lowest confidence, count below 80 %, duplicate rows that will be deleted, collisions left in the queue, and a pointer to the safer Patterns tab. Confirm stays disabled until the reviewer ticks "I understand …"; review shortcuts are off while the dialog is open. Everything lands in one `bulk` checkpoint, and the toast offers "Undo all" (undone review items go back to the queue). **Reject all:** an outlined "Reject all N" sits next to it on Review and Patterns (both act on the whole review queue on Patterns) and alone on Refused and Flagged. It opens an amber warning dialog worded per tier: refused → "these cells stay blank or invalid and still count as open issues", with a checkbox to confirm. It changes no cell, and the toast's "Undo all" reopens the items. **Privacy:** each column has "Keep as is" next to Apply (shown as a "kept unmasked" badge with Undo), and there is a "Keep all unmasked (N)" button whose dialog warns that Aadhaar/PAN would be exported in plain text (DPDP Act). Kept columns are excluded from "Mask all high-risk". Checked by `frontend/scripts/ui_accept_all.mjs`. "Show data" toggles a grid with Current / Original / Changed rows.
- **History (5B):** checkpoint timeline (you-are-here badge, undone checkpoints greyed); selecting a node filters the change log and offers Restore to here / Back to the original (two-click confirm, toast with "Go back") and Undo only this batch. Audit-chain badge (verified, entries, head hash). Change log with action and column filters, masked before → after, reason, confidence, evidence source (hover for evidence), per-entry Undo, paging.
- **Validation (6A):** the 8 do-no-harm checks in plain language (title, one-line meaning, technical detail, value) with an "n / 8 passed" badge; clean rows / score / four dimensions before → after from the full re-scan; "still open" counts. "Re-run checks" refetches. Benchmark panel: rows (1k/2k/5k) and seed, Run benchmark with step-by-step progress, six KPI tiles (false repair rate first), per-error-type table (undetected counts in amber), calibration chart (SVG: predicted vs actually correct per confidence bucket), and an honest note about planted vs real errors. The last result persists (`GET /benchmark`).
- **Diagnosis (6A):** summary from the top causes, with "Summarise with AI" on demand (quota). Source causes as cards: badge "N× more likely than elsewhere" (same number as the sentence), share of these errors, explanation, fix at the source, bar chart of the error rate per group with the culprit in red, Show rows. Pattern causes as clickable cards. Learned-rules table (rule, support, holds in, violations → rows drawer, kind).
- **Chat (6B):** the header's Chat button opens a side panel (main content shifts left on wide screens). Suggested questions; each answer shows a mode note (Gemini chose the queries / offline patterns), a collapsible "Ran N queries on your data" list with the exact tool calls and results, an optional table, and for undo requests a Confirm button that calls the real undo endpoint. History of the last 6 turns is sent with each question.
- **Privacy (6B):** findings grouped per column (free-text columns list each ID type found with counts and masked samples), risk badge, "confirmed by" checksum line, method picker (partial / hash / redact / drop) + Apply with Undo toast, "Mask all high-risk" (free text → redact, structured → partial), banner for IDs hidden in free text, method explainer cards. Masked status is derived from the change log, so an undo un-marks it.
- **Export (6B):** do-no-harm status bar (validation), clean rows before → after, open-item badges, Download all (ZIP) and six individual downloads with descriptions, inline report preview (`?inline=1`).
- Placeholder values made of one repeated digit (9999999999) are not masked: they're not personal data and the reviewer needs to see them.
- **Verification:** `frontend/scripts/ui_walkthrough.mjs` drives the installed Google Chrome headlessly (playwright-core, no browser download) through demo → setup → scan → plan → apply → drawer → dark mode → 1366×768 and fails on console errors. `frontend/scripts/ui_repair.mjs` prepares a session through the API, then checks the Repair Studio (A-key accept, row 1043 refusal, row 412 evidence, merge card, pattern bulk accept) and History (restore to original → row 412 PIN back to 40001 → Go back → 400001, per-entry undo, audit chain valid).

## 0a. Visual design (2026-11-20 redesign)

One fixed theme for every page, defined once in `src/index.css`:

| Token | Value | Used for |
|---|---|---|
| paper / card | `#F4F1EA` / `#FBFAF7` | page background / cards (Tailwind `slate-50` / `white` are remapped) |
| ink / muted / lines | `#26231E` / `#6B665C` / `#E4DFD4` | text, secondary text, borders (`slate-900/500/200`) |
| teal (brand) | `#1D4D4F`, soft `#E4EFEC` | primary buttons, active nav, links, "good" numbers |
| clay (rose) | `#B4442F`, soft `#F7E6E1` | problems, refused, high risk |
| ochre (amber) | `#B7812B`, soft `#F6EEDC` | review, warnings, duplicates |
| sage (emerald) | `#3E7B58`, soft `#E5F0E8` | repaired, passed |

- Tailwind's `slate`, `rose`, `amber`, `emerald` and `brand` scales are remapped in `@theme`, so existing classes pick up the theme; dark mode uses the same scales (warm dark `slate-950`).
- Type: **Newsreader** (serif, `font-display`) for page titles, KPI numbers and the donut total; **Inter** for everything else. Both are bundled with `@fontsource` (no Google Fonts request: the demo must work with Wi-Fi off; the rehearsal asserts no external requests).
- Shell: 232 px sidebar (logo, nav with Column types, AI status, dark-mode toggle, New file); slim top bar with file, rows, quality score and Chat; on phones the nav becomes a horizontal strip.
- Primitives (`components/ui.tsx`): `PageHeader` (serif title + lead + actions), `Card` (`title`, `subtitle`, 16 px radius, no shadow), `Kpi` (serif value), `Badge`, `Button` (10 px radius). Overview adds a clickable `Donut` (problems by type) in `components/viz.tsx`.
- Overview reads as a sentence first: "84.7% of rows are clean." before repair, "Clean rows went from 84.7% to 95.0%." after; four KPI tiles (clean rows, missing, duplicates, invalid); the plan card explains the four outcome groups (auto-fix, review, flagged, refused) in plain words.
- `frontend/scripts/ui_shots.mjs <outdir>` screenshots every page (light, dark, phone width) for visual review.

## 1. Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ DataFix  customers_dirty.csv · 10,000 rows   Score 61 → 94   LLM ● Gemini   [Chat] │
├────────────┬─────────────────────────────────────────────────────────────────┤
│ Overview   │                                                                 │
│ Diagnosis  │                        page content                             │
│ Repair     │                                                                 │
│ Privacy    │                                                                 │
│ Validation │                                                                 │
│ History    │                                                                 │
│ Export     │                                                                 │
│────────────│                                                                 │
│ Timeline ▸ │                                                                 │
└────────────┴─────────────────────────────────────────────────────────────────┘
```

- Left nav lists pages in demo order. Badge counts on Repair (review queue size) and Privacy (high-risk columns).
- Header always shows the score before → after and the LLM status pill (A13).
- Chat drawer slides in from the right on every page.
- Light theme by default (projectors wash out dark themes), dark toggle.
- Colour semantics used everywhere: green = repaired, amber = needs review, grey-striped = flagged/refused, blue = estimated, red = detected issue (unrepaired).

## 2. Pages (build order = priority)

### P1 Upload (`/`)
- Drag-drop zone (CSV, XLSX, JSON) + optional "linked table" drop zone.
- Big **"Load demo dataset"** button.
- After upload: column cards with detected semantic type, confidence and a sample; user can override a type (dropdown) before scanning. Then **Scan** button → Overview.

### P2 Overview (`/s/:sid`)
- Score gauge before → after (after shows "—" until repairs applied).
- KPI tiles: rows, missing, duplicates, invalid, inconsistent, rule violations, anomalies, PII columns.
- **Smart warnings** list (top 8) — title, explanation, affected rows, suggested action, "Show rows" (opens grid filtered).
- **Error heatmap**: columns × row blocks, CSS grid, colour by density, click a cell → grid filtered to that block/column.
- Primary CTA: **"Plan repairs"** → shows tier counts, then **"Apply N high-confidence fixes"**.

### P3 Repair Studio (`/s/:sid/repair`) — the heart of the demo
- Left: queue tabs `Review (n) · Flagged (n) · Refused (n) · Applied (n)`, filter by column/class, sort by confidence.
- Right: **Evidence card** for the selected proposal:
  - row context (the full row, the target cell highlighted, original → candidate)
  - **top-3 candidates** as radio cards with confidence bars
  - signals list with icons: `✓ PIN 400001 → Mumbai (India Post)`, `✓ city in row = Mumbai`, `✗ conflicting: …`
  - plain-English line (Gemini or template)
  - buttons: Accept (A) · Reject (R) · Custom value · Next (J/K keys)
- Refused items show the refusal reason prominently ("DataFix will not guess: 2 different phones found in orders for C-1043").
- Bottom: data grid with view toggle **Original · Current · Diff**; diff cells coloured, hover tooltip = change reason + confidence.

### P4 Diagnosis (`/s/:sid/diagnosis`)
- Root-cause cards: headline sentence with bold numbers, mini bar chart (issue rate by group), explanation, suggested fix.
- "Rules DataFix learned from your data" table: rule, support, confidence, violations, toggle.
- Pattern-cause chips (Excel sci notation, encoding, date locale…).

### P5 Validation (`/s/:sid/validation`)
- Do-no-harm checklist with pass/fail icons and values (`Valid cells changed: 0`).
- **Run self-test benchmark** button → progress → metric tiles (precision, recall, F1, repair precision, false repair rate) + per-type table + calibration chart.
- Audit chain status: "Hash chain verified · 1,284 entries · head 9f3a…".

### P6 History (`/s/:sid/history`)
- Horizontal **timeline**: `Original → Formats normalised → Duplicates merged → …`, each node with change count and score. Click node → "Restore to here". Later nodes greyed but redoable.
- Change log table (virtualised): filter by checkpoint, column, row; per-row Undo.

### P7 Privacy (`/s/:sid/privacy`)
- Table: column, PII type, rows, free-text?, risk badge, "validated by", sample (always masked in UI).
- Per row: method select (partial / hash / redact / drop) + Apply. "Mask all high-risk" button.

### P8 Export (`/s/:sid/export`)
- Summary of what's in the ZIP, unresolved counts with warning if do-no-harm has a red check.
- **Download all** + individual downloads. Preview of report.html in an iframe.

### Chat drawer (global)
- Message list; under each assistant answer, collapsible "Ran: tool(args) → result" chips and an optional table.
- `proposed_action` renders a confirm button that calls the real endpoint.
- Suggested prompt chips: "How many customers are in Pune?", "Why did row 52 change?", "Which repairs are you least sure about?", "Undo the city fixes".

## 3. Component list

`AppShell`, `ScoreGauge`, `KpiTile`, `WarningCard`, `Heatmap`, `DataGrid` (virtualised, cell-state colouring, view toggle), `ProposalList`, `EvidenceCard`, `CandidatePicker`, `SignalRow`, `RefusalBanner`, `RootCauseCard`, `RulesTable`, `CheckList`, `BenchmarkPanel`, `CalibrationChart`, `Timeline`, `ChangeLogTable`, `PiiTable`, `ChatDrawer`, `LlmStatusPill`, `EmptyState`, `LoadingSkeleton`.

## 4. UX rules

- Every number on screen is clickable to the rows behind it where feasible.
- Never show raw PII in the UI; samples always masked.
- Every mutating action shows a toast with **Undo**.
- Loading states with skeletons; scans > 1 s show a progress step list (Loading → Detecting → Diagnosing → Planning).
- Keyboard shortcuts in Repair Studio (A/R/J/K) — judges notice.
- Works at 1366×768 (common projector resolution).
