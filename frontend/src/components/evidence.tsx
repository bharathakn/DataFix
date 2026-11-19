import { useMutation, useQuery } from '@tanstack/react-query'
import { Ban, CheckCircle2, CircleAlert, Info, Lightbulb, MessageSquareQuote, Undo2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import { useSessionMutation } from '../api/hooks'
import type { Candidate, RepairProposal, RowDetail, Signal } from '../api/types'
import { cn, conf, maskSample } from '../lib/format'
import { useToast } from './toast'
import { Badge, Button, ErrorNote, Skeleton } from './ui'

export const ROW = '__row__'
const PII = new Set(['phone', 'email', 'aadhaar', 'pan', 'gstin', 'ifsc', 'text'])

export function useMasker(types: Record<string, string>) {
  return (col: string, v: string | undefined | null) => {
    if (v === undefined || v === null) return ''
    return PII.has(types[col]) ? maskSample(v, types[col]) : v
  }
}

export function ConfidenceBar({ value, className }: { value: number; className?: string }) {
  const tone = value >= 0.95 ? 'bg-emerald-500' : value >= 0.7 ? 'bg-amber-500' : 'bg-slate-400'
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700', className)}>
      <div className={cn('h-full rounded-full', tone)} style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  )
}

function SignalLine({ s }: { s: Signal }) {
  const info = s.reliability === 0 || s.score === 0
  const Icon = s.conflicting ? XCircle : info ? Info : CheckCircle2
  return (
    <li className="flex gap-2 text-sm">
      <Icon className={cn('mt-0.5 size-4 shrink-0', s.conflicting ? 'text-rose-500' : info ? 'text-slate-400' : 'text-emerald-600')} />
      <span className={cn(s.conflicting && 'text-rose-700 dark:text-rose-300', info && 'text-slate-500')}>{s.detail}</span>
    </li>
  )
}

function RowContext({ row, focus, mask, title }: { row: RowDetail; focus?: string; mask: (c: string, v: string) => string; title?: string }) {
  const vals = row.values ?? row.original
  return (
    <div>
      {title && <div className="mb-1 text-xs font-medium text-slate-500">{title}</div>}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-slate-50 p-3 text-xs sm:grid-cols-3 dark:bg-slate-800/60">
        {Object.entries(vals).map(([c, v]) => {
          const st = row.cell_state[c]
          return (
            <div key={c} className={cn('min-w-0 rounded px-1.5 py-0.5', c === focus && 'ring-2 ring-brand-500', st && `cell-${st}`)}>
              <div className="truncate text-[10px] uppercase tracking-wide text-slate-500">{c}</div>
              <div className="truncate font-medium" title={mask(c, v)}>{v === '' ? <i className="text-slate-400">blank</i> : mask(c, v)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CandidateOption({ c, i, chosen, onChoose, mask, column }:
  { c: Candidate; i: number; chosen: boolean; onChoose: () => void; mask: (c: string, v: string) => string; column: string }) {
  return (
    <label className={cn('flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition',
      chosen ? 'border-brand-500 bg-brand-50 dark:bg-brand-700/15' : 'border-slate-200 hover:border-slate-300 dark:border-slate-700')}>
      <input type="radio" checked={chosen} onChange={onChoose} className="accent-brand-600" />
      <span className="w-5 text-xs text-slate-400">{i + 1}</span>
      <span className="min-w-0 flex-1 truncate font-mono text-sm font-semibold">{mask(column, c.value) || <i>blank</i>}</span>
      <span className="w-24"><ConfidenceBar value={c.confidence} /></span>
      <span className="tabular w-10 text-right text-sm font-medium">{conf(c.confidence)}</span>
    </label>
  )
}

export function EvidenceCard({ sid, p, types, onDone }:
  { sid: string; p: RepairProposal; types: Record<string, string>; onDone: (action: 'accept' | 'reject' | 'undo') => void }) {
  const toast = useToast()
  const mask = useMasker(types)
  const [choice, setChoice] = useState(0)
  const [custom, setCustom] = useState('')
  const merge = p.column === ROW
  const survivor = merge ? Number(p.meta.survivor) : undefined
  const row = useQuery({ queryKey: [sid, 'row', p.table, p.row_id], queryFn: () => api.row(sid, p.row_id, p.table) })
  const surv = useQuery({ queryKey: [sid, 'row', p.table, survivor], queryFn: () => api.row(sid, survivor!, p.table), enabled: merge })
  const explain = useMutation({ mutationFn: () => api.explain(sid, p.proposal_id) })
  const undo = useSessionMutation(sid, (ids: string[]) => api.undoChanges(sid, ids))
  const review = useSessionMutation(sid, (b: { action: 'accept' | 'reject' | 'choose'; candidate_index?: number; custom_value?: string }) =>
    api.review(sid, p.proposal_id, b))

  const act = (action: 'accept' | 'reject' | 'choose', extra: { candidate_index?: number; custom_value?: string } = {}) =>
    review.mutate({ action, ...extra }, {
      onSuccess: (r) => {
        onDone(action === 'reject' ? 'reject' : 'accept')
        const ids = r.changes.filter((c) => c.action === 'apply').map((c) => c.change_id)
        toast(action === 'reject'
          ? { text: `Rejected: ${label} stays unchanged` }
          : { text: `Applied to ${label}`, action: ids.length ? { label: 'Undo', run: () => undo.mutate(ids) } : undefined })
      },
    })

  const label = merge ? `row ${p.row_id}` : `row ${p.row_id} · ${p.column}`
  const pending = p.status === 'pending'
  const ids = (p.meta.change_ids as string[] | undefined) ?? []
  const fills = Object.keys((p.meta.fills as Record<string, string> | undefined) ?? {})
  const remaps = ((p.meta.fk_remaps as unknown[] | undefined) ?? []).length
  const top = p.candidates[choice]

  return (
    <div className="space-y-5" data-testid="evidence">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-500" data-testid="evidence-record">record {String(p.record_id ?? p.row_id)} · {p.table} · {p.repair_class.replace('_', ' ')} · {p.algorithm.replace(/_/g, ' ')}</div>
          <h2 className="mt-1 text-lg font-semibold">
            {merge ? <>Merge duplicate row {p.row_id} into row {survivor}</> : (
              <><span className="font-mono">{p.column}</span>: <span className="cell-issue rounded px-1.5 font-mono">{mask(p.column, p.original_value) || 'blank'}</span>
                {top && <> → <span className="cell-repaired rounded px-1.5 font-mono">{mask(p.column, top.value)}</span></>}</>
            )}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={p.tier === 'auto' ? 'green' : p.tier === 'review' ? 'amber' : p.tier === 'refused' ? 'red' : 'slate'}>{p.tier}</Badge>
          <Badge tone={p.status === 'applied' ? 'green' : p.status === 'rejected' ? 'red' : 'slate'}>{p.status}</Badge>
        </div>
      </div>

      {p.refusal_reason && (
        <div className={cn('flex gap-3 rounded-lg border p-4', p.tier === 'refused'
          ? 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100'
          : 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800')}>
          {p.tier === 'refused' ? <Ban className="mt-0.5 size-5 shrink-0" /> : <CircleAlert className="mt-0.5 size-5 shrink-0" />}
          <div>
            <div className="font-semibold">{p.tier === 'refused' ? 'DataFix refused to guess' : 'Flagged, not changed'}</div>
            <div className="text-sm">{p.refusal_reason}</div>
          </div>
        </div>
      )}

      {row.isLoading ? <Skeleton className="h-28" /> : row.data && (
        merge ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <RowContext row={row.data} mask={mask} title={`Duplicate · row ${p.row_id} (removed on merge)`} />
            {surv.data && <RowContext row={surv.data} mask={mask} title={`Survivor · row ${survivor}`} />}
          </div>
        ) : <RowContext row={row.data} focus={p.column} mask={mask} title="The whole row (target cell outlined)" />
      )}
      {merge && (
        <div className="text-sm text-slate-600 dark:text-slate-400">
          On merge: {fills.length ? `fill ${fills.join(', ')} on the survivor from the duplicate; ` : ''}
          {remaps ? `re-point ${remaps} linked order(s) to the survivor; ` : ''}remove row {p.row_id}. Undo restores all of it.
        </div>
      )}

      {p.candidates.length > 0 && !merge && (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            {p.candidates.length > 1 ? `Top ${p.candidates.length} options` : 'Proposed value'}
          </div>
          <div className="space-y-2">
            {p.candidates.map((c, i) => (
              <CandidateOption key={c.value + i} c={c} i={i} chosen={choice === i} onChoose={() => setChoice(i)} mask={mask} column={p.column} />
            ))}
          </div>
        </div>
      )}

      {top && (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Evidence for {merge ? 'this merge' : `'${mask(p.column, top.value)}'`} · {conf(top.confidence)} confident</div>
          <ul className="space-y-1.5">{top.signals.map((s, i) => <SignalLine key={i} s={s} />)}</ul>
          <div className="mt-3">
            {explain.data ? (
              <div className="flex gap-2 rounded-lg bg-brand-50 p-3 text-sm dark:bg-brand-700/15">
                <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-brand-600" />
                <span>{explain.data.text} <span className="text-xs text-slate-500">({explain.data.mode})</span></span>
              </div>
            ) : (
              <Button variant="ghost" className="text-xs" loading={explain.isPending} onClick={() => explain.mutate()}>
                <Lightbulb className="size-4" />Explain in plain English
              </Button>
            )}
          </div>
        </div>
      )}

      <ErrorNote error={review.error || undo.error} />
      {pending ? (
        <div className="space-y-3 border-t border-slate-200 pt-4 dark:border-slate-800">
          <div className="flex flex-wrap gap-2">
            {p.candidates.length > 0 && (
              <Button variant="primary" loading={review.isPending} data-action="accept"
                onClick={() => choice === 0 ? act('accept') : act('choose', { candidate_index: choice })}>
                <CheckCircle2 className="size-4" />{merge ? 'Merge' : choice === 0 ? 'Accept' : `Accept option ${choice + 1}`}<kbd className="ml-1 text-[10px] opacity-70">A</kbd>
              </Button>
            )}
            <Button onClick={() => act('reject')} disabled={review.isPending} data-action="reject">
              <XCircle className="size-4" />Reject<kbd className="ml-1 text-[10px] opacity-60">R</kbd>
            </Button>
          </div>
          {!merge && (
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) act('choose', { custom_value: custom.trim() }) }}>
              <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder={p.candidates.length ? 'or type the correct value…' : 'Fix it manually: type the correct value…'}
                className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900" />
              <Button type="submit" disabled={!custom.trim() || review.isPending}>Use value</Button>
            </form>
          )}
        </div>
      ) : p.status === 'applied' && ids.length > 0 && (
        <div className="border-t border-slate-200 pt-4 dark:border-slate-800">
          <Button loading={undo.isPending} onClick={() => undo.mutate(ids, { onSuccess: () => { onDone('undo'); toast({ text: `Undid the repair on ${label}` }) } })}>
            <Undo2 className="size-4" />Undo this repair
          </Button>
          <span className="ml-3 text-xs text-slate-500">change {ids.join(', ')}</span>
        </div>
      )}
    </div>
  )
}
