import { useQuery } from '@tanstack/react-query'
import { Lock, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useSession, useSessionMutation } from '../api/hooks'
import type { MaskMethod, PiiFinding } from '../api/types'
import { useToast } from '../components/toast'
import { Badge, Button, Card, EmptyState, ErrorNote, Skeleton } from '../components/ui'
import { num } from '../lib/format'

const METHODS: { id: MaskMethod; label: string; example: string; note: string }[] = [
  { id: 'partial', label: 'Partial mask', example: '98XXXXXX45', note: 'keeps the format; records stay recognisable' },
  { id: 'hash', label: 'Hash', example: 'h_3f9a1c7e20b4', note: 'same value → same token, so duplicates stay detectable' },
  { id: 'redact', label: 'Redact', example: '[REDACTED-AADHAAR]', note: 'removes the value; in notes only the ID is replaced' },
  { id: 'drop', label: 'Drop column', example: '(column removed)', note: 'the column is left out of the export' },
]
const TYPE_LABEL: Record<string, string> = {
  aadhaar: 'Aadhaar', pan: 'PAN', gstin: 'GSTIN', phone: 'Phone', email: 'Email', ifsc: 'IFSC', card: 'Card number', bank_account: 'Bank account',
}

interface ColumnGroup { table: string; column: string; findings: PiiFinding[]; risk: 'high' | 'medium' | 'low'; freeText: boolean; masked: boolean; method: string | null }

function group(fs: PiiFinding[]): ColumnGroup[] {
  const m = new Map<string, ColumnGroup>()
  const rank = { high: 0, medium: 1, low: 2 }
  for (const f of fs) {
    const k = `${f.table}.${f.column}`
    const g = m.get(k) ?? { table: f.table, column: f.column, findings: [], risk: f.risk, freeText: f.in_free_text, masked: f.masked, method: f.method }
    g.findings.push(f)
    if (rank[f.risk] < rank[g.risk]) g.risk = f.risk
    m.set(k, g)
  }
  return [...m.values()].sort((a, b) => rank[a.risk] - rank[b.risk] || Number(b.freeText) - Number(a.freeText))
}

function ColumnRow({ sid, g }: { sid: string; g: ColumnGroup }) {
  const toast = useToast()
  const [method, setMethod] = useState<MaskMethod>(g.freeText ? 'redact' : 'partial')
  const undo = useSessionMutation(sid, (cid: string) => api.undoCheckpoint(sid, cid))
  const mask = useSessionMutation(sid, () => api.mask(sid, { column: g.column, method, table: g.table }))
  return (
    <tr className="border-t border-slate-100 align-top dark:border-slate-800">
      <td className="py-3 pr-3">
        <div className="font-mono font-medium">{g.column}</div>
        <div className="text-xs text-slate-500">{g.table}{g.freeText && ' · free text'}</div>
      </td>
      <td className="py-3 pr-3">
        <div className="space-y-1">
          {g.findings.map((f) => (
            <div key={f.pii_type} className="flex flex-wrap items-center gap-2 text-sm">
              <b>{TYPE_LABEL[f.pii_type] ?? f.pii_type}</b><span className="tabular text-slate-500">{num(f.rows)} {g.freeText ? 'found' : 'rows'}</span>
              <span className="font-mono text-xs text-slate-500">{f.sample_masked}</span>
            </div>
          ))}
          <div className="text-xs text-slate-500">confirmed by {[...new Set(g.findings.map((f) => f.validated_by))].join(', ')}</div>
        </div>
      </td>
      <td className="py-3 pr-3"><Badge tone={g.risk === 'high' ? 'red' : g.risk === 'medium' ? 'amber' : 'slate'}>{g.risk}</Badge></td>
      <td className="py-3">
        {g.masked ? (
          <div className="flex items-center gap-2"><Badge tone="green"><Lock className="size-3" />{g.method === 'drop' ? 'dropped' : `${g.method}`}</Badge></div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <select value={method} onChange={(e) => setMethod(e.target.value as MaskMethod)} aria-label={`Masking method for ${g.column}`}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900">
              {METHODS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
            <Button variant="primary" className="px-3 py-1 text-xs" loading={mask.isPending}
              onClick={() => mask.mutate(undefined, { onSuccess: (r) => toast({
                text: `${g.column}: ${method === 'drop' ? 'column dropped' : `${num(r.affected)} cells ${method === 'partial' ? 'masked' : method === 'hash' ? 'hashed' : 'redacted'}`}`,
                action: { label: 'Undo', run: () => undo.mutate(r.checkpoint.checkpoint_id) },
              }) })}>Apply</Button>
          </div>
        )}
        <ErrorNote error={mask.error} />
      </td>
    </tr>
  )
}

export default function Privacy() {
  const { sid = '' } = useParams()
  const toast = useToast()
  const { data: s } = useSession(sid)
  const pii = useQuery({ queryKey: [sid, 'privacy'], queryFn: () => api.privacy(sid), enabled: !!s && s.stage !== 'loaded' })
  const maskAll = useSessionMutation(sid, async (gs: ColumnGroup[]) => {
    let n = 0
    for (const g of gs) n += (await api.mask(sid, { column: g.column, method: g.freeText ? 'redact' : 'partial', table: g.table })).affected
    return n
  })
  if (!s) return <div className="p-6"><Skeleton className="h-96" /></div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />
  const groups = group(pii.data ?? [])
  const highOpen = groups.filter((g) => g.risk === 'high' && !g.masked)
  const hidden = (pii.data ?? []).filter((f) => f.in_free_text).reduce((a, f) => a + f.rows, 0)
  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Privacy shield</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Personal data found with checksum validation (Aadhaar: Verhoeff, cards: Luhn, GSTIN: check character), including IDs hidden in free-text notes.
            Masking is a checkpoint like any repair, so it can be undone. Raw values are never sent to the AI.
          </p>
        </div>
        <Button variant="primary" disabled={!highOpen.length} loading={maskAll.isPending}
          onClick={() => maskAll.mutate(highOpen, { onSuccess: (n) => toast({ text: `Masked ${num(n)} high-risk values in ${highOpen.length} columns` }) })}>
          <ShieldCheck className="size-4" />Mask all high-risk ({highOpen.length})
        </Button>
      </div>

      {hidden > 0 && (
        <div className="flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100">
          <ShieldAlert className="mt-0.5 size-5 shrink-0" />
          <div><b>{num(hidden)} identity numbers are hidden inside free-text fields</b>, where ordinary column-level tools never look.
            Each one was confirmed with its checksum, so random digit strings don't count.</div>
        </div>
      )}

      <Card title="Personal data found">
        <ErrorNote error={pii.error || maskAll.error} />
        {pii.isLoading ? <Skeleton className="h-48" /> : groups.length === 0 ? <EmptyState title="No personal data detected" /> : (
          <table className="w-full text-left">
            <thead className="text-xs text-slate-500"><tr><th className="pb-2">Column</th><th className="pb-2">What was found</th><th className="pb-2">Risk</th><th className="pb-2">Protect</th></tr></thead>
            <tbody>{groups.map((g) => <ColumnRow key={`${g.table}.${g.column}`} sid={sid} g={g} />)}</tbody>
          </table>
        )}
      </Card>

      <Card title="Masking methods">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {METHODS.map((m) => (
            <div key={m.id} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              <div className="font-medium">{m.label}</div>
              <div className="mt-1 font-mono text-sm text-brand-700 dark:text-brand-100">{m.example}</div>
              <div className="mt-1 text-xs text-slate-500">{m.note}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
