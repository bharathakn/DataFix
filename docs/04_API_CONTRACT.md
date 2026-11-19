# 04 · API Contract

Base URL `http://localhost:8000/api`. JSON everywhere except uploads (multipart) and downloads. All session routes are under `/sessions/{sid}`. Errors: `{"error": {"code": "NOT_FOUND", "message": "…"}}` with matching HTTP status.

Frontend types in `frontend/src/api/types.ts` mirror these shapes exactly. Change this doc first, then both sides.

## As built (Phase 4) — read this first

Implemented in `backend/api/routes.py`, verified by `scripts/smoke_api.py` (46 endpoint calls through the full demo flow). Differences from the original draft below:

| Change | Detail |
|---|---|
| Flow is explicit | `POST /sessions` (or `/sessions/demo`) only loads the file and guesses column types (~0.3 s / 2.7 s). Then `POST /scan` (body `{overrides: {column: type}}`, also runs diagnosis + privacy scan), then `POST /repair/plan`. Calling a step too early returns **409** `INVALID_STATE` with a message saying which step to run first. |
| New: `GET /sessions` | Recent sessions (from the pickle directory). |
| New: `GET /sessions/{sid}/proposals/groups?tier=review&column=` | **Bulk review by pattern**: identical `(column, from → to)` suggestions grouped with `count`, `avg_confidence`, `proposal_ids`; accept them with `POST /review/bulk`. |
| New: `GET /sessions/{sid}/proposals/{pid}/explain` | `{text, mode}`: plain-English evidence sentence (Gemini or template). |
| New: `POST /sessions/{sid}/changes/undo` | Body `{change_ids: [...]}`; used to confirm the chatbot's "undo the city fixes". |
| `GET /diagnosis?narrative=true` | Returns `{causes: RootCause[], narrative, mode}` (was a bare list). Narrative is Gemini or a template; can take 2–15 s, so the UI should request it separately and show the template first. |
| `POST /scan` response | Adds `dimensions`, `rules`, `tables` (per-table score and counts). |
| `SessionSummary` (5A) | Once scanned also carries `dimensions`, `dimensions_now` (fast estimate from unresolved issues), `pii_columns`, `tiers`, `pending` (by tier), `applied`, `checkpoints`, `rows_main_pending`, `score_now`. |
| `GET /rows` | Extra filters `table`, `state` (cell state), `row_ids=1,2,3`. `cell_state` lists **only non-clean cells**; new `original` map gives before-values of repaired / estimated / masked cells. `view=diff` = rows with ≥ 1 applied change. |
| `GET /row/{row_id}` | `{row_id, table, deleted, record_id, values, original, cell_state, issues, proposals, changes}`. |
| `GET /proposals` | Extra filters `table`, `algorithm`, `sort=row|confidence|-confidence`; items include `record_id` (the dataset's own ID). |
| `POST /review/bulk` | Returns `{applied, change_ids, checkpoint, score_now}`; `change_ids` lets the UI undo exactly that bulk action. |
| New: `GET /review/accept-all/preview?tier=review&column=` | What "Accept all" would do: `{count, skipped, by_column, avg_confidence, min_confidence, below_80, expected_wrong, merges}`. `expected_wrong` = Σ(1 − confidence), the number of wrong fixes to expect if confidence is calibrated. `skipped` = suggestions that collide with a more confident one (same cell, or a merge whose row is already merged away). |
| New: `POST /review/accept-all` | Body `{tier: "review", column?: string}`. Accepts every pending suggestion of the tier (optionally one column) server-side as **one** checkpoint (kind `bulk`), so one undo reverts it. Returns `{applied, skipped, checkpoint, score_now}`. Takes ~1–5 s for 3k suggestions on the demo, longer on big files. |
| `POST /repair/plan` | Returns `{tiers, by_class, duration_ms}` plus `auto/review/flag/refused` at top level. Rejected (409) once repairs exist. |
| `POST /privacy/mask` | Body `{column, method, table?, pii_type?}`; returns `{checkpoint, affected, findings}`. Unknown column → 409. `GET /privacy` derives `masked` / `method` from the live change log (undo un-masks). |
| Concurrency | Every `/sessions/{sid}/…` route holds that session's re-entrant lock for the whole request, so reads never interleave with a repair (the current-table cache is updated in place; pandas is not thread-safe). |
| `POST /benchmark` | Body `{sample_rows (100–20000), error_rate, seed}`; result shape in `types.ts` (`BenchmarkResult`). `GET /benchmark` returns the last result or `null`. |
| `RootCause.rate_by_group` | Up to 8 groups, most issues first (the culprit group always shows). `times_elsewhere` = rate in the group ÷ rate everywhere else (null = only in this group). |
| `GET /export/{kind}?inline=1` | Serve with `Content-Disposition: inline` (used to preview the HTML report in an iframe). |
| `GET /api/debug/inflight` | Requests currently running with elapsed seconds; requests slower than 5 s are also logged. Use it if the UI seems stuck. |
| `GET /llm/status?ping=true` | `{provider, model, models, keys, ok, last_error, using_backup_key, cooling_down, recent_calls}`. |
| Chat `proposed_action.kind` | `undo_checkpoint` (payload `checkpoint_id`) or `undo_changes` (payload `change_ids`). |
| Errors | 404 `NOT_FOUND` (unknown session / proposal / change / checkpoint / export kind), 409 `INVALID_STATE` (wrong order, already applied, no PII in column), 422 `BAD_REQUEST` (body validation). |
| Timings (demo, laptop) | scan 6–7 s · plan 0.8 s · apply-auto 1.8 s · validation 5.5 s · benchmark 4.5 s · export zip 2.7 s · everything else < 350 ms. |

## Sessions and data

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/sessions` | multipart: `file` (required), `linked_file` (optional, e.g. orders), `linked_name` | `SessionSummary` |
| POST | `/sessions/demo` | — | `SessionSummary` for bundled demo data |
| GET | `/sessions/{sid}` | — | `SessionSummary` |
| GET | `/sessions/{sid}/rows` | `offset`, `limit` (≤ 500), `view=current\|original\|diff`, `filter_issue_type`, `column` | `RowsPage` |
| GET | `/sessions/{sid}/row/{row_id}` | — | `RowDetail` (values, issues, changes for that row) |

```ts
type SessionSummary = {
  session_id: string; filename: string; rows: number; columns: ColumnInfo[];
  linked_tables: { name: string; rows: number; join_key: string | null }[];
  file_sha256: string; created_at: string;
};
type RowsPage = {
  total: number; offset: number;
  columns: string[];
  rows: { row_id: number; values: Record<string, string>;
          cell_state: Record<string, "clean"|"issue"|"repaired"|"review"|"flagged"|"estimated"> }[];
};
```

## Scan, diagnosis, heatmap

| Method | Path | Returns |
|---|---|---|
| POST | `/sessions/{sid}/scan` | `ScanResult` |
| GET | `/sessions/{sid}/issues` | `?type=&column=&offset=&limit=` → `{total, items: Issue[]}` |
| GET | `/sessions/{sid}/warnings` | `Warning[]` (grouped, plain language) |
| GET | `/sessions/{sid}/diagnosis` | `RootCause[]` |
| GET | `/sessions/{sid}/heatmap` | `?blocks=50` → `Heatmap` |
| GET | `/sessions/{sid}/rules` | learned dependencies + active cross-field rules |

```ts
type ScanResult = {
  quality_score: number;               // 0..100
  counts: Record<IssueType, number>;
  by_column: Record<string, Record<IssueType, number>>;
  pii_columns: number; warnings: number; duration_ms: number;
};
type Warning = { warning_id: string; title: string; explanation: string; affected_rows: number;
                 sample_row_ids: number[]; suggested_action: string; severity: "high"|"medium"|"low";
                 issue_type: IssueType; column: string | null };
type RootCause = { cause_id: string; title: string;          // "71 of 73 blank city values come from source = mobile_app and import_batch = B07"
                   kind: "source_lift"|"pattern";
                   issue_type: string; issue_kind: string | null; column: string | null;
                   group: { columns: string[]; value: string } | null;   // value "mobile_app · B07" for pairs
                   share_of_issues: number | null; lift: number | null;
                   explanation: string; suggested_fix: string; issue_count: number;
                   rate_by_group: { value: string; rows: number; issues: number; rate: number }[] };
type Heatmap = { columns: string[]; block_size: number;
                 cells: number[][] /* [block][column] error density 0..1 */ };
type LearnedRule = { rule_id: string; kind: "fd"|"crossfield"|"user";
                     description: string; support: number; confidence: number; violations: number; enabled: boolean };
```

## Repair

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/sessions/{sid}/repair/plan` | `{thresholds?: {auto: number, review: number}}` | `PlanSummary` |
| GET | `/sessions/{sid}/proposals` | `?tier=auto\|review\|flag\|refused&column=&status=&offset=&limit=` | `{total, items: RepairProposal[]}` |
| POST | `/sessions/{sid}/repair/apply-auto` | — | `{checkpoints: Checkpoint[], applied: number}` |
| POST | `/sessions/{sid}/review/{proposal_id}` | `{action: "accept"\|"reject"\|"choose", candidate_index?: number, custom_value?: string}` | `{proposal: RepairProposal, change?: Change}` |
| POST | `/sessions/{sid}/review/bulk` | `{proposal_ids: string[], action: "accept"\|"reject"}` | `{applied: number, checkpoint?: Checkpoint}` |

```ts
type PlanSummary = { auto: number; review: number; flag: number; refused: number;
                     by_class: Record<string, number>; duration_ms: number };
// RepairProposal, Candidate, Signal exactly as 03_ARCHITECTURE.md §4
```

## History and audit

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/sessions/{sid}/checkpoints` | — | `Checkpoint[]` with `active: boolean` |
| POST | `/sessions/{sid}/checkpoints/{cid}/restore` | — | `Checkpoint[]` |
| POST | `/sessions/{sid}/checkpoints/{cid}/undo` | — | `Checkpoint[]` (undo just that batch) |
| POST | `/sessions/{sid}/changes/{change_id}/undo` | — | `Change` |
| GET | `/sessions/{sid}/changes` | `?row_id=&column=&checkpoint_id=&offset=&limit=` | `{total, items: Change[]}` |
| GET | `/sessions/{sid}/audit/verify` | — | `{valid: boolean, entries: number, head_hash: string, broken_at?: string}` |

## Validation and benchmark

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/sessions/{sid}/validation` | — | `Validation` |
| POST | `/sessions/{sid}/benchmark` | `{sample_rows?: 2000, error_rate?: 0.05, seed?: 42}` | `BenchmarkResult` |

```ts
type Check = { name: string; passed: boolean; value: string; detail: string };
type Dimensions = { completeness: number; validity: number; consistency: number; uniqueness: number; clean_rows: number };
type Validation = { score_before: number; score_after: number; checks: Check[]; passed: boolean;
                    dimensions_before: Dimensions; dimensions_after: Dimensions;
                    unresolved: { review: number; flag: number; refused: number };
                    remaining_errors: number; still_failing_after_repair: number; surfaced: number; duration_ms: number };
// checks: valid_cells_changed, schema_unchanged, row_count_explained, distribution_stable,
//         no_new_errors, referential_integrity, idempotent, audit_chain_valid
type BenchmarkResult = {
  injected: number;
  detection: { precision: number; recall: number; f1: number };
  repair: { precision: number; auto_precision: number; coverage: number; false_repair_rate: number;
            correct: number; wrong: number; estimates: number; estimate_mean_abs_error: number | null; false_repairs: number };
  sample_rows: number; error_rate: number; dup_rate: number;
  by_error_type: { type: string; injected: number; detected: number; repaired_correctly: number }[];
  calibration: { bucket: string; predicted: number; actual: number; n: number }[];
  duration_ms: number; seed: number;
};
```

## Privacy

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/sessions/{sid}/privacy` | — | `PiiFinding[]` |
| POST | `/sessions/{sid}/privacy/mask` | `{column: string, pii_type?: string, method: "partial"\|"redact"\|"hash"\|"drop"}` | `{checkpoint: Checkpoint, affected: number}` |

```ts
type PiiFinding = { table: string; column: string; pii_type: "aadhaar"|"pan"|"gstin"|"phone"|"email"|"ifsc"|"card"|"bank_account";
                    rows: number; in_free_text: boolean; risk: "high"|"medium"|"low";
                    validated_by: string;           // "Verhoeff checksum", "Luhn", "regex"
                    sample_masked: string; masked: boolean; method?: string };
```

## Chat

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/sessions/{sid}/chat` | `{message: string, history?: {role, text}[]}` | `ChatReply` |
| GET | `/llm/status` | — | `{provider: "gemini"\|"offline", model?: string, ok: boolean}` |

```ts
type ChatReply = { text: string;
                   tool_calls: { name: string; args: object; result_preview: object }[];
                   table?: { columns: string[]; rows: string[][] };
                   proposed_action?: { kind: "undo_checkpoint"|"undo_column"|"filter"; label: string; payload: object };
                   mode: "gemini"|"offline" };
```

A `proposed_action` is never executed by the chat route; the UI shows a confirm button that calls the normal history/repair endpoints.

## Export

| Method | Path | Returns |
|---|---|---|
| GET | `/sessions/{sid}/export/zip` | `datafix_output.zip` |
| GET | `/sessions/{sid}/export/{kind}` | `kind` ∈ `cleaned_csv`, `highlighted_xlsx`, `report_html`, `change_log_csv`, `privacy_csv`, `recipe_json` |
