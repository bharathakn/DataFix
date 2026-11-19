import { useQuery } from '@tanstack/react-query'
import { Ban, CheckCheck, CircleAlert, Layers, ListChecks, Table2, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useSession, useSessionMutation } from '../api/hooks'
import type { ProposalGroup, RepairProposal } from '../api/types'
import { DataGrid } from '../components/DataGrid'
import { ConfidenceBar, EvidenceCard, ROW, useMasker } from '../components/evidence'
import { useToast } from '../components/toast'
import { Button, Card, EmptyState, ErrorNote, Skeleton, Spinner } from '../components/ui'
import { cn, conf, num } from '../lib/format'

type Tab = 'review' | 'flag' | 'refused' | 'applied' | 'patterns'
const TABS: { id: Tab; label: string; icon: typeof ListChecks }[] = [
  { id: 'review', label: 'Review', icon: ListChecks }, { id: 'patterns', label: 'Patterns', icon: Layers },
  { id: 'refused', label: 'Refused', icon: Ban }, { id: 'flag', label: 'Flagged', icon: CircleAlert },
  { id: 'applied', label: 'Applied', icon: CheckCheck },
]

function QueueItem({ p, active, onClick, mask }: { p: RepairProposal; active: boolean; onClick: () => void; mask: (c: string, v: string) => string }) {
  const merge = p.column === ROW
  const top = p.candidates[0]
  return (
    <button onClick={onClick} data-pid={p.proposal_id}
      className={cn('w-full border-l-2 px-3 py-2.5 text-left transition', active
        ? 'border-brand-600 bg-brand-50 dark:bg-brand-700/15' : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50')}>
      <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
        <span className="truncate">{String(p.record_id ?? p.row_id)} · {merge ? 'duplicate row' : p.column}{p.table !== 'customers' && p.table ? ` · ${p.table}` : ''}</span>
        {top && <span className="tabular font-medium text-slate-700 dark:text-slate-300">{conf(p.confidence)}</span>}
      </div>
      <div className="mt-0.5 truncate font-mono text-sm">
        {merge ? `merge into row ${String(p.meta.survivor)}` : <>
          <span className="text-rose-600 dark:text-rose-400">{mask(p.column, p.original_value) || 'blank'}</span>
          {top ? <> → <span className="text-emerald-700 dark:text-emerald-400">{mask(p.column, top.value)}</span></> : null}
        </>}
      </div>
      {!top && p.refusal_reason && <div className="mt-0.5 truncate text-xs text-slate-500" title={p.refusal_reason}>{p.refusal_reason}</div>}
      {top && <ConfidenceBar value={p.confidence} className="mt-1.5" />}
    </button>
  )
}

function Patterns({ sid }: { sid: string }) {
  const toast = useToast()
  const groups = useQuery({ queryKey: [sid, 'groups'], queryFn: () => api.groups(sid, { tier: 'review' }) })
  const bulk = useSessionMutation(sid, ({ ids, action }: { ids: string[]; action: 'accept' | 'reject' }) => api.bulkReview(sid, ids, action))
  const undo = useSessionMutation(sid, (ids: string[]) => api.undoChanges(sid, ids))
  const { data: s } = useSession(sid)
  const mask = useMasker(Object.fromEntries((s?.columns ?? []).map((c) => [c.name, c.semantic_type])))
  if (groups.isLoading) return <Skeleton className="h-64" />
  const gs = groups.data ?? []
  if (!gs.length) return <EmptyState title="No repeated patterns waiting for review" />
  const run = (g: ProposalGroup, action: 'accept' | 'reject') => bulk.mutate({ ids: g.proposal_ids, action }, {
    onSuccess: (r) => toast({
      text: `${action === 'accept' ? 'Accepted' : 'Rejected'} ${num(g.count)} × ${g.column === ROW ? 'duplicate merge' : `'${mask(g.column, g.from)}'`}`,
      action: action === 'accept' && r.change_ids.length ? { label: 'Undo', run: () => undo.mutate(r.change_ids) } : undefined,
    }),
  })
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Identical suggestions grouped together, so a reviewer can approve a whole pattern at once instead of one cell at a time.
      </p>
      <ErrorNote error={bulk.error} />
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
        {gs.map((g) => (
          <div key={`${g.column}|${g.from}|${g.to}|${g.algorithm}`} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="tabular w-12 text-right text-lg font-semibold">{num(g.count)}×</div>
            <div className="min-w-0 flex-1">
              <div className="truncate font-mono text-sm">
                {g.column === ROW ? 'merge likely duplicate rows' : <>
                  <span className="text-slate-500">{g.column}:</span> <span className="text-rose-600">{mask(g.column, g.from) || 'blank'}</span> →{' '}
                  <span className="text-emerald-700 dark:text-emerald-400">{mask(g.column, g.to)}</span></>}
              </div>
              <div className="text-xs text-slate-500">{g.algorithm.replace(/_/g, ' ')} · avg {conf(g.avg_confidence)} · lowest {conf(g.min_confidence)}</div>
            </div>
            <Button variant="primary" className="text-xs" disabled={bulk.isPending} onClick={() => run(g, 'accept')}>Accept all</Button>
            <Button className="text-xs" disabled={bulk.isPending} onClick={() => run(g, 'reject')}>Reject all</Button>
          </div>
        ))}
      </div>
    </div>
  )
}

/** "Accept all" for the whole review queue: a deliberate, warned, single-checkpoint action. */
function AcceptAllDialog({ sid, column, onClose, onAccepted }: { sid: string; column: string; onClose: () => void; onAccepted: () => void }) {
  const toast = useToast()
  const [sure, setSure] = useState(false)
  const preview = useQuery({ queryKey: [sid, 'accept-all-preview', column], queryFn: () => api.acceptAllPreview(sid, column || undefined) })
  const undo = useSessionMutation(sid, (cid: string) => api.undoCheckpoint(sid, cid))
  const accept = useSessionMutation(sid, () => api.acceptAll(sid, column || undefined))
  const busy = accept.isPending
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])
  const p = preview.data
  const scope = column === ROW ? 'duplicate-row ' : column ? `'${column}' ` : ''
  const go = () => accept.mutate(undefined, {
    onSuccess: (r) => {
      onAccepted()
      onClose()
      toast({
        text: `Accepted ${num(r.applied)} ${scope}suggestions as checkpoint ${r.checkpoint?.checkpoint_id ?? ''}${r.skipped ? ` · ${num(r.skipped)} left for review` : ''}`,
        action: r.checkpoint ? { label: 'Undo all', run: () => undo.mutate(r.checkpoint!.checkpoint_id) } : undefined,
      })
    },
  })
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="accept-all-title">
      <div className="absolute inset-0 bg-slate-900/50" onClick={() => !busy && onClose()} />
      <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-rose-300 bg-white shadow-2xl dark:border-rose-800 dark:bg-slate-900">
        <header className="flex items-start gap-3 border-b border-rose-200 bg-rose-50 px-5 py-4 dark:border-rose-900 dark:bg-rose-950/40">
          <TriangleAlert className="mt-0.5 size-6 shrink-0 text-rose-600" />
          <div>
            <h2 id="accept-all-title" className="font-semibold text-rose-900 dark:text-rose-100">
              Accept {p ? num(p.count) : 'all'} {scope}suggestions without reviewing them?
            </h2>
            <p className="mt-1 text-sm text-rose-800 dark:text-rose-200">
              These are <b>review</b> suggestions: DataFix was only 70–95% sure, which is why it did not apply them on its own.
            </p>
          </div>
        </header>
        <div className="space-y-3 px-5 py-4 text-sm">
          {preview.isLoading ? <Skeleton className="h-32" /> : <ErrorNote error={preview.error} />}
          {p && p.count === 0 && <p>Nothing to accept here.</p>}
          {p && p.count > 0 && <>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-rose-50 p-2 dark:bg-rose-950/30">
                <div className="tabular text-xl font-semibold text-rose-700 dark:text-rose-300">≈ {num(p.expected_wrong)}</div>
                <div className="text-xs text-slate-600 dark:text-slate-400">likely wrong fixes</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800/60">
                <div className="tabular text-xl font-semibold">{p.min_confidence !== null ? conf(p.min_confidence) : '–'}</div>
                <div className="text-xs text-slate-600 dark:text-slate-400">lowest confidence</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800/60">
                <div className="tabular text-xl font-semibold">{num(p.below_80)}</div>
                <div className="text-xs text-slate-600 dark:text-slate-400">below 80%</div>
              </div>
            </div>
            <ul className="list-disc space-y-1 pl-5 text-slate-700 dark:text-slate-300">
              <li>The estimate adds up (1 − confidence) over all {num(p.count)} suggestions. Nobody will look at the evidence for any of them.</li>
              {p.merges > 0 && <li><b>{num(p.merges)} duplicate rows will be deleted</b> and the records pointing at them re-pointed to the surviving row.</li>}
              {p.skipped > 0 && <li>{num(p.skipped)} suggestions collide with a more confident one (same cell, or a row already merged away) and stay in the queue.</li>}
              <li>Columns: {Object.entries(p.by_column).slice(0, 6).map(([c, n]) => `${c} ${num(n)}`).join(' · ')}{Object.keys(p.by_column).length > 6 ? ' · …' : ''}</li>
              <li>Safer: the <b>Patterns</b> tab accepts one identical fix at a time, or filter by column first.</li>
              <li>Everything goes into <b>one checkpoint</b>, so a single “Undo all” (here or in History) reverts it.</li>
            </ul>
            <label className="flex items-start gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <input type="checkbox" className="mt-0.5" checked={sure} disabled={busy} onChange={(e) => setSure(e.target.checked)} />
              <span>I understand about {num(p.expected_wrong)} of these {num(p.count)} changes may be wrong and nobody will review them.</span>
            </label>
          </>}
          <ErrorNote error={accept.error} />
          {busy && <Spinner label={`Applying ${p ? num(p.count) : ''} changes… this can take a minute on large files. Keep this tab open.`} />}
        </div>
        <footer className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800">
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="danger" disabled={!sure || !p?.count} loading={busy} onClick={go}>
            Accept all {p ? num(p.count) : ''}
          </Button>
        </footer>
      </div>
    </div>
  )
}

export default function RepairStudio() {
  const { sid = '' } = useParams()
  const { data: s } = useSession(sid)
  const [tab, setTab] = useState<Tab>('review')
  const [column, setColumn] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<'current' | 'original' | 'diff' | null>(null)
  const [strongFirst, setStrongFirst] = useState(true)
  const [acceptAll, setAcceptAll] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const types = useMemo(() => Object.fromEntries((s?.columns ?? []).map((c) => [c.name, c.semantic_type])), [s])
  const mask = useMasker(types)

  const q = tab === 'applied' ? { status: 'applied', sort: 'row' }
    : { tier: tab, status: 'pending', sort: tab === 'review' ? (strongFirst ? '-confidence' : 'confidence') : 'row' }
  const list = useQuery({
    queryKey: [sid, 'proposals', tab, column, strongFirst], enabled: tab !== 'patterns' && !!s?.tiers,
    queryFn: () => api.proposals(sid, { ...q, column: column || undefined, limit: 500 }),
    placeholderData: (prev) => prev,
  })
  const items = useMemo(() => list.data?.items ?? [], [list.data])
  const current = items.find((p) => p.proposal_id === selected) ?? items[0]
  const idx = current ? items.indexOf(current) : -1

  // after an accept/reject the item leaves the list; keep the cursor at the same position
  const pendingIndex = useRef<number | null>(null)
  useEffect(() => {
    if (pendingIndex.current !== null && items.length) {
      const i = Math.min(pendingIndex.current, items.length - 1)
      setSelected(items[i].proposal_id)
      pendingIndex.current = null
    }
  }, [items])
  useEffect(() => {
    listRef.current?.querySelector(`[data-pid="${current?.proposal_id}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [current?.proposal_id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || e.metaKey || e.ctrlKey) return
      if (document.querySelector('[role="dialog"]')) return
      if (e.key === 'j' && idx < items.length - 1) setSelected(items[idx + 1].proposal_id)
      if (e.key === 'k' && idx > 0) setSelected(items[idx - 1].proposal_id)
      const ev = document.querySelector('[data-testid="evidence"]')
      if (e.key === 'a') (ev?.querySelector('[data-action="accept"]') as HTMLButtonElement | null)?.click()
      if (e.key === 'r') (ev?.querySelector('[data-action="reject"]') as HTMLButtonElement | null)?.click()
      if (['1', '2', '3'].includes(e.key)) (ev?.querySelectorAll('input[type=radio]')[Number(e.key) - 1] as HTMLInputElement | undefined)?.click()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [idx, items])

  if (!s) return <div className="p-6"><Skeleton className="h-96" /></div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />
  if (s.stage === 'scanned') return <Navigate to={`/s/${sid}`} replace />

  const pend = s.pending ?? {}
  const counts: Record<Tab, number | undefined> = { review: pend.review, flag: pend.flag, refused: pend.refused, applied: s.applied, patterns: undefined }
  const columns = [...new Set(s.columns.map((c) => c.name))]

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Repair Studio</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">Every suggestion shows its evidence. Keys: <kbd>A</kbd> accept · <kbd>R</kbd> reject · <kbd>J</kbd>/<kbd>K</kbd> next/previous · <kbd>1–3</kbd> pick an option.</p>
        </div>
        <Button onClick={() => setView(view ? null : 'diff')}><Table2 className="size-4" />{view ? 'Hide data' : 'Show data'}</Button>
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => { setTab(id); setSelected(null) }}
            className={cn('-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm', tab === id
              ? 'border-brand-600 font-medium text-brand-700 dark:text-brand-100' : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200')}>
            <Icon className="size-4" />{label}{counts[id] !== undefined && <span className="tabular rounded-full bg-slate-100 px-1.5 text-xs dark:bg-slate-800">{num(counts[id])}</span>}
          </button>
        ))}
        {tab === 'review' && !!list.data?.total && (
          <Button variant="danger" className="mb-1 ml-auto px-2.5 py-1 text-xs" onClick={() => setAcceptAll(true)}>
            <CheckCheck className="size-3.5" />Accept all {num(list.data.total)}{column ? ` ${column === ROW ? 'duplicates' : column}` : ''}
          </Button>
        )}
        {tab === 'review' && (
          <button onClick={() => { setStrongFirst(!strongFirst); setSelected(null) }}
            className={cn('mb-1 rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800', !list.data?.total && 'ml-auto')}>
            {strongFirst ? 'Most confident first' : 'Least confident first'} ⇅
          </button>
        )}
        {tab !== 'patterns' && (
          <select value={column} onChange={(e) => { setColumn(e.target.value); setSelected(null) }} aria-label="Filter by column"
            className={cn('mb-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900', tab !== 'review' && 'ml-auto')}>
            <option value="">All columns</option>
            <option value={ROW}>Duplicate rows</option>
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
      </div>

      {tab === 'patterns' ? <Card><Patterns sid={sid} /></Card> : (
        <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
          <Card className="overflow-hidden [&>div]:p-0">
            <div ref={listRef} className="max-h-[70vh] divide-y divide-slate-100 overflow-auto dark:divide-slate-800">
              {list.isLoading ? <div className="p-4"><Skeleton className="h-64" /></div>
                : items.length === 0 ? <EmptyState title={tab === 'review' ? 'Review queue is empty' : 'Nothing here'}>
                  {tab === 'review' && 'Every suggestion has been decided.'}</EmptyState>
                : items.map((p) => <QueueItem key={p.proposal_id} p={p} mask={mask} active={p === current} onClick={() => setSelected(p.proposal_id)} />)}
            </div>
            {list.data && list.data.total > items.length && (
              <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-500 dark:border-slate-800">Showing {num(items.length)} of {num(list.data.total)}; filter by column to narrow.</div>
            )}
          </Card>
          <Card>
            <ErrorNote error={list.error} />
            {current ? <EvidenceCard key={current.proposal_id + current.status} sid={sid} p={current} types={types}
              onDone={(a) => { if (a !== 'undo') pendingIndex.current = idx }} />
              : !list.isLoading && <EmptyState title="Select an item" />}
          </Card>
        </div>
      )}

      {acceptAll && <AcceptAllDialog sid={sid} column={column} onClose={() => setAcceptAll(false)} onAccepted={() => setSelected(null)} />}

      {view && (
        <Card title="Data" action={
          <div className="flex rounded-md border border-slate-300 p-0.5 text-xs dark:border-slate-700">
            {(['current', 'original', 'diff'] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} className={cn('rounded px-2.5 py-1', view === v && 'bg-brand-600 text-white')}>
                {v === 'diff' ? 'Changed rows' : v === 'current' ? 'Current' : 'Original'}
              </button>
            ))}
          </div>}>
          <DataGrid key={view} sid={sid} filter={{ view }} />
        </Card>
      )}
    </div>
  )
}
