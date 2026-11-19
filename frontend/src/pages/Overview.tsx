import { AlertTriangle, ArrowRight, CheckCircle2, Search, ShieldAlert, Wand2, Wrench } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useDiagnosis, useHeatmap, useSession, useSessionMutation, useWarnings } from '../api/hooks'
import type { SessionSummary, Warning } from '../api/types'
import { DataGrid, type GridFilter } from '../components/DataGrid'
import { useToast } from '../components/toast'
import { Badge, Button, Card, Drawer, EmptyState, ErrorNote, Kpi, Skeleton } from '../components/ui'
import { DimensionBars, Heatmap, ScoreGauge } from '../components/viz'
import { num } from '../lib/format'

interface GridView { title: string; filter: GridFilter; column?: string }

function NextStep({ s, sid }: { s: SessionSummary; sid: string }) {
  const toast = useToast()
  const plan = useSessionMutation(sid, () => api.plan(sid))
  const apply = useSessionMutation(sid, () => api.applyAuto(sid))
  const restore = useSessionMutation(sid, (cid: string) => api.restore(sid, cid))
  const t = s.tiers ?? {}
  const p = s.pending ?? {}

  if (s.stage === 'scanned') {
    return (
      <Card title="Next: plan repairs">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          DataFix will propose a fix for every problem it found, each backed by evidence and a confidence score, or
          refuse when the evidence isn't there. Nothing changes until you apply.
        </p>
        <Button className="mt-4" variant="primary" loading={plan.isPending} onClick={() => plan.mutate(undefined)}>
          <Wand2 className="size-4" />Plan repairs
        </Button>
        <ErrorNote error={plan.error} />
      </Card>
    )
  }
  const tiers = (
    <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
      <TierBox label="Auto-fix" sub="≥ 95% confident" n={t.auto} tone="text-emerald-600" />
      <TierBox label="Review" sub="70–95%" n={t.review} tone="text-amber-600" />
      <TierBox label="Flagged" sub="unusual, not changed" n={t.flag} tone="text-slate-600 dark:text-slate-300" />
      <TierBox label="Refused" sub="not enough evidence" n={t.refused} tone="text-rose-600" />
    </div>
  )
  if (s.stage === 'planned') {
    return (
      <Card title="Repair plan ready">
        {tiers}
        <Button className="mt-4" variant="primary" loading={apply.isPending}
          onClick={() => apply.mutate(undefined, {
            onSuccess: (r) => toast({
              text: `Applied ${num(r.applied)} fixes in ${r.checkpoints.length} checkpoints`,
              action: { label: 'Undo', run: () => restore.mutate('K00') },
            }),
          })}>
          <Wand2 className="size-4" />Apply {num(t.auto)} high-confidence fixes
        </Button>
        <ErrorNote error={apply.error} />
      </Card>
    )
  }
  return (
    <Card title={<span className="flex items-center gap-2"><CheckCircle2 className="size-4 text-emerald-600" />Repairs applied</span>}>
      {tiers}
      <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
        <b className="tabular">{num(s.applied)}</b> fixes applied across {Math.max(0, (s.checkpoints ?? 1) - 1)} checkpoints.{' '}
        <b className="tabular">{num(p.review)}</b> suggestions wait for your review; {num((p.refused ?? 0) + (p.flag ?? 0))} items were
        flagged or refused and left unchanged.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={`/s/${sid}/repair`}><Button variant="primary"><Wrench className="size-4" />Open Repair Studio</Button></Link>
        <Link to={`/s/${sid}/validation`}><Button>Prove it: validation</Button></Link>
      </div>
    </Card>
  )
}

function TierBox({ label, sub, n, tone }: { label: string; sub: string; n?: number; tone: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
      <div className={`tabular text-xl font-semibold ${tone}`}>{num(n)}</div>
      <div className="text-xs font-medium">{label}</div>
      <div className="text-[11px] text-slate-500">{sub}</div>
    </div>
  )
}

function WarningRow({ w, onShow }: { w: Warning; onShow: () => void }) {
  const tone = w.severity === 'high' ? 'red' : w.severity === 'medium' ? 'amber' : 'slate'
  return (
    <li className="flex items-start gap-3 py-3">
      <AlertTriangle className={`mt-0.5 size-4 shrink-0 ${w.severity === 'high' ? 'text-rose-500' : w.severity === 'medium' ? 'text-amber-500' : 'text-slate-400'}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{w.title}</span><Badge tone={tone}>{w.severity}</Badge>
        </div>
        <div className="mt-0.5 truncate text-xs text-slate-500" title={w.explanation}>{w.explanation}</div>
        <div className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">→ {w.suggested_action}</div>
      </div>
      <Button variant="ghost" className="shrink-0 text-xs" onClick={onShow}>Show rows</Button>
    </li>
  )
}

export default function Overview() {
  const { sid = '' } = useParams()
  const { data: s, error } = useSession(sid)
  const warnings = useWarnings(sid, s?.stage)
  const heat = useHeatmap(sid, s?.stage)
  const diag = useDiagnosis(sid, s?.stage)
  const [grid, setGrid] = useState<GridView | null>(null)
  const [showAll, setShowAll] = useState(false)

  if (error) return <div className="p-6"><ErrorNote error={error} /></div>
  if (!s) return <div className="grid gap-4 p-6 lg:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-40" />)}</div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />

  const c = s.counts ?? {}
  const repaired = s.stage === 'repairing'
  const d0 = s.dimensions!
  const d1 = repaired ? s.dimensions_now : undefined
  const open = (title: string, filter: GridFilter, column?: string) => setGrid({ title, filter, column })
  const ws = warnings.data ?? []

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <Card className="flex items-center justify-center">
          <ScoreGauge before={d0.clean_rows} after={d1?.clean_rows} />
          <p className="mt-2 text-center text-xs text-slate-500">
            Share of rows with no problem at all{repaired ? ' (estimate; Validation re-checks everything)' : ''}.
          </p>
        </Card>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
          <Kpi label="Rows" value={num(s.rows)} hint={s.linked_tables.map((t) => `+ ${num(t.rows)} ${t.name}`).join(' ')} />
          <Kpi label="Missing" value={num((c.missing ?? 0) + (c.disguised_missing ?? 0))} tone="red"
            hint={`${num(c.disguised_missing)} are placeholders`} onClick={() => open('Missing values', { issue_type: 'missing' })} />
          <Kpi label="Duplicates" value={num((c.duplicate ?? 0) + (c.near_duplicate ?? 0))} tone="red"
            hint={`${num(c.near_duplicate)} near-duplicates`} onClick={() => open('Duplicate rows', { issue_type: 'duplicate' })} />
          <Kpi label="Invalid" value={num(c.invalid_format)} tone="red" onClick={() => open('Invalid values', { issue_type: 'invalid_format' })} />
          <Kpi label="Inconsistent" value={num(c.inconsistent)} tone="amber" onClick={() => open('Inconsistent values', { issue_type: 'inconsistent' })} />
          <Kpi label="Rule violations" value={num((c.fd_violation ?? 0) + (c.crossfield ?? 0))} tone="amber"
            hint="rules learned from the data" onClick={() => open('Rule violations', { issue_type: 'fd_violation' })} />
          <Kpi label="Unusual values" value={num(c.anomaly)} hint="flagged, never changed" onClick={() => open('Unusual values', { issue_type: 'anomaly' })} />
          <Link to={`/s/${sid}/privacy`} className="contents">
            <Kpi label="Personal data" value={<span className="flex items-center gap-1.5"><ShieldAlert className="size-5 text-violet-500" />{num(s.pii_columns)}</span>}
              hint="columns with PII" onClick={() => {}} />
          </Link>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <NextStep s={s} sid={sid} />
        <Card title="Quality dimensions" action={<span className="text-xs text-slate-500">% of rows without the problem</span>}>
          <DimensionBars before={d0} after={d1} />
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={`Smart warnings (${ws.length})`}
          action={ws.length > 8 && <Button variant="ghost" className="text-xs" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : 'Show all'}</Button>}>
          {warnings.isLoading ? <Skeleton className="h-48" /> : ws.length === 0 ? <EmptyState title="No problems found" /> : (
            <ul className="-my-3 divide-y divide-slate-100 dark:divide-slate-800">
              {(showAll ? ws : ws.slice(0, 8)).map((w) => (
                <WarningRow key={w.warning_id} w={w} onShow={() => open(w.title,
                  w.issue_type === 'duplicate' || w.issue_type === 'near_duplicate'
                    ? { issue_type: w.issue_type } : { issue_type: w.issue_type, column: w.column ?? undefined }, w.column ?? undefined)} />
              ))}
            </ul>
          )}
        </Card>
        <Card title="Why the data is dirty" action={<Link to={`/s/${sid}/diagnosis`} className="text-xs text-brand-600 hover:underline">Full diagnosis</Link>}>
          {diag.isLoading ? <Skeleton className="h-40" /> : (
            <ul className="space-y-3">
              {(diag.data?.causes ?? []).filter((x) => x.kind === 'source_lift').slice(0, 3).map((x) => (
                <li key={x.cause_id} className="text-sm">
                  <div className="flex gap-2"><Search className="mt-0.5 size-4 shrink-0 text-brand-600" /><span className="font-medium">{x.title}</span></div>
                  <div className="ml-6 mt-0.5 text-xs text-slate-500">{x.suggested_fix}</div>
                </li>
              ))}
              <li><Link to={`/s/${sid}/diagnosis`} className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline">
                See all causes and the rules DataFix learned <ArrowRight className="size-3.5" /></Link></li>
            </ul>
          )}
        </Card>
      </div>

      <Card title="Where the errors are" action={<span className="text-xs text-slate-500">columns × row blocks</span>}>
        {heat.data ? (
          <Heatmap data={heat.data} onPick={(b, col) => {
            const size = heat.data!.block_size
            const ids = Array.from({ length: size }, (_, i) => b * size + i).join(',')
            open(`Rows ${num(b * size)}–${num((b + 1) * size - 1)} · ${col}`,
              col === '(duplicates)' ? { row_ids: ids, issue_type: 'duplicate' } : { row_ids: ids, column: col }, col)
          }} />
        ) : <Skeleton className="h-40" />}
      </Card>

      <Drawer open={!!grid} onClose={() => setGrid(null)} title={grid?.title} wide>
        {grid && <DataGrid key={JSON.stringify(grid.filter)} sid={sid} filter={grid.filter} highlightColumn={grid.column} />}
      </Drawer>
    </div>
  )
}
