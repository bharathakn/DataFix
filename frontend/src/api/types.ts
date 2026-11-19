// Mirrors docs/04_API_CONTRACT.md. Change the contract first, then backend and this file.

export type IssueType =
  | 'missing' | 'disguised_missing' | 'invalid_format' | 'inconsistent' | 'fd_violation'
  | 'crossfield' | 'anomaly' | 'duplicate' | 'near_duplicate' | 'sparse_column'

export type CellState = 'clean' | 'issue' | 'repaired' | 'review' | 'flagged' | 'estimated' | 'masked'
export type Tier = 'auto' | 'review' | 'flag' | 'refused'
export type ProposalStatus = 'pending' | 'applied' | 'rejected' | 'undone'
export type Stage = 'loaded' | 'scanned' | 'planned' | 'repairing'

export interface ApiError { error: { code: string; message: string } }

export interface ColumnInfo {
  name: string; semantic_type: string; type_confidence: number; null_count: number; distinct: number
  sample: string[]; overridden: boolean
}

export interface SessionSummary {
  session_id: string; table: string; filename: string; rows: number; rows_current: number
  columns: ColumnInfo[]; linked_tables: { name: string; rows: number; join_key: string | null }[]
  file_sha256: string; created_at: string; stage: Stage; version: number
  quality_score?: number; score_now?: number; counts?: Partial<Record<IssueType, number>>
  dimensions?: Dimensions; dimensions_now?: Dimensions; pii_columns?: number
  tiers?: Partial<Record<Tier, number>>; pending?: Partial<Record<Tier, number>>; applied?: number
  checkpoints?: number; rows_main_pending?: number
}

export interface Dimensions {
  completeness: number; validity: number; consistency: number; uniqueness: number; clean_rows: number
}

export interface ScanResult {
  quality_score: number; dimensions: Dimensions; counts: Partial<Record<IssueType, number>>
  by_column: Record<string, Partial<Record<IssueType, number>>>; pii_columns: number; warnings: number
  rules: number; duration_ms: number
  tables: Record<string, { rows: number; quality_score: number; counts: Partial<Record<IssueType, number>> }>
}

export interface Issue {
  issue_id: string; row_id: number | null; column: string | null; type: IssueType; severity_weight: number
  detector: string; message: string; value: string | null; meta: Record<string, unknown>
}

export interface Warning {
  warning_id: string; title: string; explanation: string; affected_rows: number; sample_row_ids: number[]
  suggested_action: string; severity: 'high' | 'medium' | 'low'; issue_type: IssueType
  issue_kind: string | null; column: string | null
}

export interface RootCause {
  cause_id: string; title: string; kind: 'source_lift' | 'pattern'; issue_type: string; issue_kind: string | null
  column: string | null; group: { columns: string[]; value: string } | null
  share_of_issues: number | null; lift: number | null; times_elsewhere: number | null; explanation: string; suggested_fix: string
  issue_count: number; rate_by_group: { value: string; rows: number; issues: number; rate: number }[]
}

export interface Diagnosis { causes: RootCause[]; narrative: string | null; mode: 'gemini' | 'groq' | 'offline' | null }

export interface Heatmap { columns: string[]; block_size: number; cells: number[][]; max: number }

export interface LearnedRule {
  rule_id: string; kind: 'fd' | 'crossfield' | 'user'; lhs: string; rhs: string; description: string
  support: number; confidence: number; violations: number; enabled: boolean
}

export interface RowsPage {
  total: number; offset: number; columns: string[]
  rows: {
    row_id: number; values: Record<string, string>
    cell_state: Record<string, CellState>   // only non-clean cells are listed
    original: Record<string, string>        // before-values of repaired / estimated / masked cells
  }[]
}

export interface Signal { name: string; score: number; reliability: number; detail: string; conflicting: boolean }
export interface Candidate { value: string; confidence: number; signals: Signal[] }

export interface RepairProposal {
  proposal_id: string; table: string; issue_ids: string[]; row_id: number; column: string  // "__row__" = merge
  original_value: string; candidates: Candidate[]; tier: Tier; repair_class: string; algorithm: string
  refusal_reason: string | null; status: ProposalStatus; meta: Record<string, unknown>; confidence: number
  record_id?: string | number
}

export interface ProposalGroup {
  table: string; column: string; algorithm: string; from: string; to: string; count: number
  avg_confidence: number; min_confidence: number; proposal_ids: string[]
}

export interface PlanSummary {
  tiers: Partial<Record<Tier, number>>; by_class: Record<string, number>; duration_ms: number
  auto?: number; review?: number; flag?: number; refused?: number
}

export interface Change {
  change_id: string; checkpoint_id: string; proposal_id: string | null; table: string; row_id: number
  column: string; original_value: string; new_value: string; reason: string; evidence: string[]; source: string
  confidence: number; algorithm: string; actor: string; action: 'apply' | 'undo' | 'redo' | 'reject'
  target: string | null; timestamp: string; prev_hash: string; hash: string; status: string
  record_id?: string | number | null
}

export interface AcceptAllPreview {
  count: number; skipped: number; by_column: Record<string, number>; avg_confidence: number | null
  min_confidence: number | null; below_80: number; expected_wrong: number; merges: number
}

export interface Checkpoint {
  checkpoint_id: string; label: string; kind: 'original' | 'auto' | 'review' | 'mask' | 'user'
  change_ids: string[]; created_at: string; quality_score: number; changes: number; active: boolean
}

export interface RowDetail {
  row_id: number; table: string; deleted: boolean; record_id: string | number
  values: Record<string, string> | null; original: Record<string, string>
  cell_state: Record<string, CellState>; issues: Issue[]; proposals: RepairProposal[]; changes: Change[]
}

export interface Check { name: string; passed: boolean; value: string; detail: string }

export interface Validation {
  score_before: number; score_after: number; checks: Check[]; passed: boolean
  dimensions_before: Dimensions; dimensions_after: Dimensions
  unresolved: { review: number; flag: number; refused: number }
  remaining_errors: number; still_failing_after_repair: number; surfaced: number; duration_ms: number
}

export interface BenchmarkResult {
  sample_rows: number; injected: number; seed: number; error_rate: number; dup_rate: number
  detection: { precision: number; recall: number; f1: number }
  repair: {
    precision: number; auto_precision: number; coverage: number; correct: number; wrong: number
    estimates: number; estimate_mean_abs_error: number | null; false_repairs: number; false_repair_rate: number
  }
  by_error_type: { type: string; injected: number; detected: number; repaired_correctly: number }[]
  calibration: { bucket: string; predicted: number; actual: number; n: number }[]
  duration_ms: number
}

export interface PiiFinding {
  table: string; column: string; pii_type: 'aadhaar' | 'pan' | 'gstin' | 'phone' | 'email' | 'ifsc' | 'card' | 'bank_account'
  rows: number; in_free_text: boolean; risk: 'high' | 'medium' | 'low'; validated_by: string
  sample_masked: string; masked: boolean; method: MaskMethod | null
  kept: boolean  // the user chose to leave this column unmasked
}
export type MaskMethod = 'partial' | 'redact' | 'hash' | 'drop'

export interface ChatReply {
  text: string
  tool_calls: { name: string; args: Record<string, unknown>; result_preview: unknown }[]
  table: { columns: string[]; rows: string[][] } | null
  proposed_action: { kind: 'undo_checkpoint' | 'undo_changes'; label: string;
                     payload: { checkpoint_id?: string; change_ids?: string[] } } | null
  mode: 'gemini' | 'groq' | 'offline'
}

export interface LlmStatus {
  provider: 'gemini' | 'groq' | 'offline'; model: string | null; models?: string[]; keys: number; ok: boolean | null
  last_error: string | null; using_backup_key: boolean; cooling_down?: Record<string, number>
  backup?: { provider: 'groq'; configured: boolean; model: string; cooling_down: number; last_error: string | null }
}
