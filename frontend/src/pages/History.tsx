import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, History as HistoryIcon, RotateCcw, ShieldCheck, ShieldX, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useCheckpoints, useSession, useSessionMutation } from '../api/hooks'
import type { Checkpoint } from '../api/types'
import { useMasker } from '../components/evidence'
import { useToast } from '../components/toast'
import { Badge, Button, Card, EmptyState, ErrorNote, Skeleton } from '../components/ui'
import { cn, conf, num } from '../lib/format'

const PAGE = 50

function Timeline({ sid, cps, selected, onSelect }: { sid: string; cps: Checkpoint[]; selected: string | null; onSelect: (id: string | null) => void }) {
  const toast = useToast()
  const [confirm, setConfirm] = useState<string | null>(null)
  const restore = useSessionMutation(sid, (cid: string) => api.restore(sid, cid))
  const undoBatch = useSessionMutation(sid, (cid: string) => api.undoCheckpoint(sid, cid))
  // the "current" position = last active checkpoint
  const head = [...cps].reverse().find((k) => k.active)?.checkpoint_id
  return (
    <div>
      <div className="overflow-x-auto pb-2">
        <ol className="flex min-w-max items-stretch">
          {cps.map((k, i) => {
            const isHead = k.checkpoint_id === head
            return (
              <li key={k.checkpoint_id} className="flex items-center">
                {i > 0 && <div className={cn('h-0.5 w-8', k.active ? 'bg-brand-500' : 'bg-slate-300 dark:bg-slate-700')} />}
                <button onClick={() => onSelect(selected === k.checkpoint_id ? null : k.checkpoint_id)}
                  className={cn('h-[104px] w-44 rounded-lg border p-3 text-left align-top transition',
                    selected === k.checkpoint_id ? 'border-brand-600 ring-2 ring-brand-200 dark:ring-brand-700' : 'border-slate-200 dark:border-slate-700',
                    k.active ? 'bg-white dark:bg-slate-900' : 'bg-slate-50 opacity-60 dark:bg-slate-900/40')}>
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="font-mono">{k.checkpoint_id}</span>
                    {isHead ? <Badge tone="blue">you are here</Badge> : !k.active && <Badge>undone</Badge>}
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm font-medium" title={k.label}>{k.label}</div>
                  <div className="tabular mt-1 text-xs text-slate-500">{k.kind === 'original' ? 'untouched upload' : `${num(k.changes)} changes`} · score {k.quality_score}</div>
                </button>
              </li>
            )
          })}
        </ol>
      </div>
      {selected && (() => {
        const k = cps.find((c) => c.checkpoint_id === selected)
        if (!k) return null
        return (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/60">
            <span className="font-medium">{k.checkpoint_id} · {k.label}</span>
            <span className="text-slate-500">Change log below is filtered to this checkpoint.</span>
            <div className="ml-auto flex gap-2">
              {confirm === k.checkpoint_id ? (
                <>
                  <span className="self-center text-xs text-slate-600 dark:text-slate-300">
                    {k.kind === 'original' ? 'Undo every change?' : 'Keep only checkpoints up to here?'}
                  </span>
                  <Button variant="primary" loading={restore.isPending} onClick={() => restore.mutate(k.checkpoint_id, {
                    onSuccess: () => { setConfirm(null); toast({ text: `Restored to ${k.checkpoint_id} · ${k.label}`, action: head ? { label: 'Go back', run: () => restore.mutate(head) } : undefined }) },
                  })}>Confirm</Button>
                  <Button onClick={() => setConfirm(null)}>Cancel</Button>
                </>
              ) : (
                <>
                  <Button onClick={() => setConfirm(k.checkpoint_id)} disabled={k.checkpoint_id === head && k.active}>
                    <RotateCcw className="size-4" />{k.kind === 'original' ? 'Back to the original' : k.active ? 'Restore to here' : 'Re-apply up to here'}
                  </Button>
                  {k.kind !== 'original' && k.active && (
                    <Button loading={undoBatch.isPending} onClick={() => undoBatch.mutate(k.checkpoint_id, {
                      onSuccess: () => toast({ text: `Undid batch ${k.label}` }),
                    })}><Undo2 className="size-4" />Undo only this batch</Button>
                  )}
                </>
              )}
            </div>
          </div>
        )
      })()}
      <ErrorNote error={restore.error || undoBatch.error} />
    </div>
  )
}

export default function History() {
  const { sid = '' } = useParams()
  const { data: s } = useSession(sid)
  const toast = useToast()
  const cps = useCheckpoints(sid, !!s && s.stage !== 'loaded')
  const audit = useQuery({ queryKey: [sid, 'audit'], queryFn: () => api.auditVerify(sid), enabled: !!s?.tiers })
  const [selected, setSelected] = useState<string | null>(null)
  const [column, setColumn] = useState('')
  const [action, setAction] = useState('')
  const [page, setPage] = useState(0)
  const q = { checkpoint_id: selected ?? undefined, column: column || undefined, action: action || undefined, offset: page * PAGE, limit: PAGE }
  const changes = useQuery({ queryKey: [sid, 'changes', q], queryFn: () => api.changes(sid, q), enabled: !!s?.tiers, placeholderData: (p) => p })
  const undo = useSessionMutation(sid, (id: string) => api.undoChange(sid, id))
  const types = useMemo(() => Object.fromEntries((s?.columns ?? []).map((c) => [c.name, c.semantic_type])), [s])
  const mask = useMasker(types)

  if (!s) return <div className="p-6"><Skeleton className="h-96" /></div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />
  const total = changes.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE))

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">History</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">Every repair batch is a checkpoint. Jump back or forward at any time; the original file is never touched.</p>
        </div>
        {audit.data && (
          <div className={cn('flex items-center gap-2 rounded-lg px-3 py-2 text-sm', audit.data.valid
            ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200' : 'bg-rose-50 text-rose-800 dark:bg-rose-950 dark:text-rose-200')}
            title={`head hash ${audit.data.head_hash}`}>
            {audit.data.valid ? <ShieldCheck className="size-4" /> : <ShieldX className="size-4" />}
            {audit.data.valid ? <>Audit chain verified · {num(audit.data.entries)} entries · <span className="font-mono text-xs">{audit.data.head_hash.slice(0, 10)}…</span></>
              : <>Audit chain BROKEN at {audit.data.broken_at}</>}
          </div>
        )}
      </div>

      <Card title="Checkpoint timeline">
        {cps.isLoading ? <Skeleton className="h-24" /> : (cps.data?.length ?? 0) <= 1
          ? <EmptyState icon={<HistoryIcon className="size-8" />} title="No repairs yet">Apply fixes on the Overview to create checkpoints.</EmptyState>
          : <Timeline sid={sid} cps={cps.data!} selected={selected} onSelect={(id) => { setSelected(id); setPage(0) }} />}
      </Card>

      <Card title={`Change log${selected ? ` · ${selected}` : ''}`} action={
        <div className="flex items-center gap-2">
          <select value={action} onChange={(e) => { setAction(e.target.value); setPage(0) }} aria-label="Filter by action"
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900">
            <option value="">All entries</option><option value="apply">Repairs</option><option value="undo">Undos</option>
            <option value="redo">Redos</option><option value="reject">Rejections</option>
          </select>
          <select value={column} onChange={(e) => { setColumn(e.target.value); setPage(0) }} aria-label="Filter by column"
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900">
            <option value="">All columns</option><option value="__row__">Row merges</option>
            {s.columns.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>}>
        <ErrorNote error={changes.error || undo.error} />
        <div className="overflow-auto">
          <table className="min-w-full text-xs">
            <thead className="text-left text-slate-500">
              <tr className="border-b border-slate-200 dark:border-slate-800">
                {['Change', 'Batch', 'Action', 'Record', 'Column', 'Before → after', 'Confidence', 'Evidence source', 'By', ''].map((h) => <th key={h} className="px-2 py-2 font-semibold">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {(changes.data?.items ?? []).map((c) => (
                <tr key={c.change_id} className={cn('border-b border-slate-100 dark:border-slate-800', c.action === 'apply' && c.status === 'undone' && 'opacity-50')}>
                  <td className="px-2 py-1.5 font-mono">{c.change_id}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-500">{c.checkpoint_id}</td>
                  <td className="px-2 py-1.5"><Badge tone={c.action === 'apply' ? (c.status === 'undone' ? 'slate' : 'green') : c.action === 'reject' ? 'red' : 'blue'}>
                    {c.action === 'apply' && c.status === 'undone' ? 'undone' : c.action}</Badge></td>
                  <td className="px-2 py-1.5">{String(c.record_id ?? (c.row_id >= 0 ? c.row_id : '—'))}{c.table !== s.table && <span className="text-slate-400"> · {c.table}</span>}</td>
                  <td className="px-2 py-1.5 font-mono">{c.column === '__row__' ? 'row' : c.column}</td>
                  <td className="max-w-[340px] px-2 py-1.5" title={c.reason}>
                    <span className="font-mono text-rose-600 dark:text-rose-400">{c.column === '__row__' ? '' : mask(c.column, c.original_value) || 'blank'}</span>
                    {' → '}<span className="font-mono text-emerald-700 dark:text-emerald-400">{c.column === '__row__' ? 'merged' : mask(c.column, c.new_value) || 'blank'}</span>
                    <div className="truncate text-slate-500">{c.reason}</div>
                  </td>
                  <td className="tabular px-2 py-1.5">{c.action === 'apply' ? conf(c.confidence) : ''}</td>
                  <td className="max-w-[180px] truncate px-2 py-1.5 text-slate-500" title={c.evidence.join('\n')}>{c.source}</td>
                  <td className="px-2 py-1.5 text-slate-500">{c.actor}</td>
                  <td className="px-2 py-1.5">
                    {c.action === 'apply' && c.status === 'applied' && (
                      <Button variant="ghost" className="px-2 py-1 text-xs" disabled={undo.isPending}
                        onClick={() => undo.mutate(c.change_id, { onSuccess: () => toast({ text: `Undid ${c.change_id}` }) })}>
                        <Undo2 className="size-3.5" />Undo</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {changes.data && total === 0 && <div className="p-6 text-center text-sm text-slate-500">No entries.</div>}
        </div>
        <div className="mt-3 flex items-center justify-end gap-2 text-sm text-slate-500">
          <span className="tabular">{num(total)} entries</span>
          <Button variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
          <span className="tabular">{page + 1} / {pages}</span>
          <Button variant="ghost" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight className="size-4" /></Button>
        </div>
      </Card>
    </div>
  )
}
