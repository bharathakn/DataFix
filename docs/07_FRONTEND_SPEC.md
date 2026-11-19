# 07 · Frontend Specification

React 18 + Vite + TypeScript + Tailwind + shadcn/ui. TanStack Query for server state, TanStack Table + `@tanstack/react-virtual` for the grid, Recharts for charts, lucide-react icons, react-router.

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
