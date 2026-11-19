# 04 · API Contract

Base URL `http://localhost:8000/api`. JSON everywhere except uploads (multipart) and downloads. All session routes are under `/sessions/{sid}`. Errors: `{"error": {"code": "NOT_FOUND", "message": "…"}}` with matching HTTP status.

Frontend types in `frontend/src/api/types.ts` mirror these shapes exactly. Change this doc first, then both sides.

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
type RootCause = { cause_id: string; title: string;          // "71 of 73 blank cities come from mobile_app batch B07"
                   kind: "source_lift"|"pattern";
                   issue_type: IssueType; column: string | null;
                   group: { column: string; value: string } | null;
                   share_of_issues: number; lift: number;
                   explanation: string; suggested_fix: string; issue_count: number };
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
type Validation = { score_before: number; score_after: number; checks: Check[];
                    unresolved: { review: number; flag: number; refused: number } };
// checks: valid_cells_changed, schema_unchanged, row_count_explained, distribution_stable,
//         no_new_errors, referential_integrity, idempotent, audit_chain_valid
type BenchmarkResult = {
  injected: number;
  detection: { precision: number; recall: number; f1: number };
  repair: { precision: number; coverage: number; false_repair_rate: number };
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
type PiiFinding = { column: string; pii_type: "aadhaar"|"pan"|"gstin"|"phone"|"email"|"ifsc"|"card"|"bank_account";
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
