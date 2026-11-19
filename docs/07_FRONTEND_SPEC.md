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
- **Repair Studio (5B):** tabs Review · Patterns · Refused · Flagged · Applied with counts; column filter (incl. "Duplicate rows"); review queue sorted most-confident-first by default (toggle). Evidence card: record line, original → chosen value, refusal / flag banner, the whole row as a grid with the target cell outlined, top-3 options as radio cards with confidence bars, evidence list (✓ supporting, ✗ conflicting, ℹ explanatory), "Explain in plain English" on demand (saves Gemini quota), Accept / Reject / custom value, Undo toast; applied items get "Undo this repair". Duplicate merges show duplicate and survivor rows side by side with what the merge fills and re-points. Keys: A accept, R reject, J/K next/previous, 1–3 choose an option (buttons carry `data-action`). Patterns tab = bulk review by pattern with Accept all / Reject all and Undo. "Show data" toggles a grid with Current / Original / Changed rows.
- **History (5B):** checkpoint timeline (you-are-here badge, undone checkpoints greyed); selecting a node filters the change log and offers Restore to here / Back to the original (two-click confirm, toast with "Go back") and Undo only this batch. Audit-chain badge (verified, entries, head hash). Change log with action and column filters, masked before → after, reason, confidence, evidence source (hover for evidence), per-entry Undo, paging.
- Placeholder values made of one repeated digit (9999999999) are not masked: they're not personal data and the reviewer needs to see them.
- **Verification:** `frontend/scripts/ui_walkthrough.mjs` drives the installed Google Chrome headlessly (playwright-core, no browser download) through demo → setup → scan → plan → apply → drawer → dark mode → 1366×768 and fails on console errors. `frontend/scripts/ui_repair.mjs` prepares a session through the API, then checks the Repair Studio (A-key accept, row 1043 refusal, row 412 evidence, merge card, pattern bulk accept) and History (restore to original → row 412 PIN back to 40001 → Go back → 400001, per-entry undo, audit chain valid).

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
