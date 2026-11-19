import type {
  BenchmarkResult, Change, ChatReply, Checkpoint, Diagnosis, Heatmap, LearnedRule, LlmStatus, PiiFinding, PlanSummary,
  ProposalGroup, RepairProposal, RowDetail, RowsPage, ScanResult, SessionSummary, Validation, Warning,
} from './types'

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type Query = Record<string, string | number | boolean | undefined | null>

function qs(q?: Query): string {
  if (!q) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

async function req<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const init: RequestInit = { method }
  if (body instanceof FormData) init.body = body
  else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  let res: Response
  try {
    res = await fetch(`/api${path}${qs(query)}`, init)
  } catch {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the DataFix backend. Is it running on port 8000?')
  }
  if (!res.ok) {
    let code = 'HTTP', message = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j?.error) ({ code, message } = j.error)
    } catch { /* not JSON */ }
    throw new ApiError(res.status, code, message)
  }
  return res.json() as Promise<T>
}

const S = (sid: string) => `/sessions/${sid}`

export const api = {
  health: () => req<{ status: string; llm: string }>('GET', '/health'),
  llmStatus: () => req<LlmStatus>('GET', '/llm/status'),

  createDemo: () => req<SessionSummary>('POST', '/sessions/demo'),
  upload: (file: File, linked?: File | null) => {
    const fd = new FormData()
    fd.append('file', file)
    if (linked) fd.append('linked_file', linked)
    return req<SessionSummary>('POST', '/sessions', fd)
  },
  session: (sid: string) => req<SessionSummary>('GET', S(sid)),

  scan: (sid: string, overrides: Record<string, string> = {}) => req<ScanResult>('POST', `${S(sid)}/scan`, { overrides }),
  warnings: (sid: string) => req<Warning[]>('GET', `${S(sid)}/warnings`),
  diagnosis: (sid: string, narrative = false) => req<Diagnosis>('GET', `${S(sid)}/diagnosis`, undefined, { narrative }),
  heatmap: (sid: string, blocks = 40) => req<Heatmap>('GET', `${S(sid)}/heatmap`, undefined, { blocks }),
  rules: (sid: string) => req<LearnedRule[]>('GET', `${S(sid)}/rules`),
  rows: (sid: string, q: Query) => req<RowsPage>('GET', `${S(sid)}/rows`, undefined, q),
  row: (sid: string, rowId: number, table?: string) => req<RowDetail>('GET', `${S(sid)}/row/${rowId}`, undefined, { table }),

  plan: (sid: string) => req<PlanSummary>('POST', `${S(sid)}/repair/plan`, {}),
  proposals: (sid: string, q: Query) => req<{ total: number; items: RepairProposal[] }>('GET', `${S(sid)}/proposals`, undefined, q),
  groups: (sid: string, q: Query) => req<ProposalGroup[]>('GET', `${S(sid)}/proposals/groups`, undefined, q),
  explain: (sid: string, pid: string) => req<{ text: string; mode: string }>('GET', `${S(sid)}/proposals/${pid}/explain`),
  applyAuto: (sid: string) => req<{ checkpoints: Checkpoint[]; applied: number; score_now: number }>('POST', `${S(sid)}/repair/apply-auto`),
  review: (sid: string, pid: string, body: { action: 'accept' | 'reject' | 'choose'; candidate_index?: number; custom_value?: string }) =>
    req<{ proposal: RepairProposal; changes: Change[]; score_now: number }>('POST', `${S(sid)}/review/${pid}`, body),
  bulkReview: (sid: string, ids: string[], action: 'accept' | 'reject') =>
    req<{ applied: number; change_ids: string[] }>('POST', `${S(sid)}/review/bulk`, { proposal_ids: ids, action }),

  checkpoints: (sid: string) => req<Checkpoint[]>('GET', `${S(sid)}/checkpoints`),
  restore: (sid: string, cid: string) => req<Checkpoint[]>('POST', `${S(sid)}/checkpoints/${cid}/restore`),
  undoCheckpoint: (sid: string, cid: string) => req<Checkpoint[]>('POST', `${S(sid)}/checkpoints/${cid}/undo`),
  undoChange: (sid: string, changeId: string) => req<unknown>('POST', `${S(sid)}/changes/${changeId}/undo`),
  undoChanges: (sid: string, ids: string[]) => req<unknown>('POST', `${S(sid)}/changes/undo`, { change_ids: ids }),

  changes: (sid: string, q: Query) => req<{ total: number; items: Change[] }>('GET', `${S(sid)}/changes`, undefined, q),
  auditVerify: (sid: string) => req<{ valid: boolean; entries: number; head_hash: string; broken_at: string | null }>('GET', `${S(sid)}/audit/verify`),
  validation: (sid: string) => req<Validation>('GET', `${S(sid)}/validation`),
  benchmark: (sid: string, body: { sample_rows?: number; seed?: number } = {}) => req<BenchmarkResult>('POST', `${S(sid)}/benchmark`, body),
  privacy: (sid: string) => req<PiiFinding[]>('GET', `${S(sid)}/privacy`),
  chat: (sid: string, message: string, history: { role: 'user' | 'assistant'; text: string }[]) =>
    req<ChatReply>('POST', `${S(sid)}/chat`, { message, history }),
  exportUrl: (sid: string, kind: string) => `/api${S(sid)}/export/${kind}`,
}
