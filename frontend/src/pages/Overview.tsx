import { ArrowRight, CheckCircle2, Search, ShieldAlert, Wand2, Wrench } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useDiagnosis, useHeatmap, useSession, useSessionMutation, useWarnings } from '../api/hooks'
import type { SessionSummary, Warning } from '../api/types'
import { DataGrid, type GridFilter } from '../components/DataGrid'
import { useToast } from '../components/toast'
import { Badge, Button, Card, Drawer, EmptyState, ErrorNote, Kpi, PageHeader, Skeleton } from '../components/ui'
import { DimensionBars, Donut, Heatmap, ScoreGauge } from '../components/viz'
import { num, pct } from '../lib/format'

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
      <Card title="Next: plan repairs" subtitle="Nothing changes until you apply">
        <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          DataFix will propose a fix for every problem it found, each backed by evidence and a confidence score, or
          refuse when the evidence isn't there. Each proposal lands in one of four groups:
        </p>
        <ul className="mt-3 grid gap-2 text-[13px] sm:grid-cols-2">
          {[['bg-brand-600', 'Auto-fix', '95% or more confident: applied in one click, still undoable'],
            ['bg-amber-500', 'Review', '70–95%: you accept or reject each one'],
            ['bg-slate-400', 'Flagged', 'unusual but possible: shown, never changed'],
            ['bg-rose-500', 'Refused', 'not enough evidence: DataFix will not guess']].map(([dot, t, d]) => (
            <li key={t} className="flex gap-2.5 rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-slate-800/60">
              <span className={`mt-1.5 size-2 shrink-0 rounded-full ${dot}`} />
              <span><b>{t}</b><span className="block text-slate-500">{d}</span></span>
            </li>
          ))}
        </ul>
        <Button className="mt-4" variant="primary" loading={plan.isPending} onClick={() => plan.mutate(undefined)}>
          <Wand2 className="size-4" />Plan repairs
        </Button>
        <ErrorNote error={plan.error} />
      </Card>
    )
  }
  const tiers = (
    <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
      <TierBox label="Auto-fix" sub="≥ 95% confident" n={t.auto} tone="text-brand-600 dark:text-brand-300" />
      <TierBox label="Review" sub="70–95%" n={t.review} tone="text-amber-500" />
      <TierBox label="Flagged" sub="unusual, not changed" n={t.flag} tone="text-slate-600 dark:text-slate-300" />
      <TierBox label="Refused" sub="not enough evidence" n={t.refused} tone="text-rose-500" />
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
    <div className="rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60">
      <div className={`tabular font-display text-[26px] leading-none ${tone}`}>{num(n)}</div>
      <div className="mt-2 text-xs font-semibold">{label}</div>
      <div className="text-[11px] text-slate-500">{sub}</div>
    </div>
  )
}

function WarningRow({ w, onShow }: { w: Warning; onShow: () => void }) {
  const tone = w.severity === 'high' ? 'red' : w.severity === 'medium' ? 'amber' : 'slate'
  return (
    <li className="flex items-start gap-3.5 py-3.5">
      <Badge tone={tone} className="mt-0.5 w-[62px] justify-center capitalize">{w.severity}</Badge>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{w.title}</div>
        <div className="mt-1 line-clamp-2 text-[13px] leading-snug text-slate-500" title={w.explanation}>{w.explanation} {w.suggested_action}</div>
      </div>
      <button className="shrink-0 text-sm font-medium text-brand-600 hover:underline dark:text-brand-300" onClick={onShow}>Show rows</button>
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

  const sources = (diag.data?.causes ?? []).filter((x) => x.kind === 'source_lift')
  const missing = (c.missing ?? 0) + (c.disguised_missing ?? 0)
  const dups = (c.duplicate ?? 0) + (c.near_duplicate ?? 0)
  const headline = d1 && d1.clean_rows !== d0.clean_rows
    ? <>Clean rows went from {pct(d0.clean_rows)} to <span className="text-brand-600 dark:text-brand-300">{pct(d1.clean_rows)}</span>.</>
    : <>{pct(d0.clean_rows)} of rows are clean.{sources.length > 0 && <> {sources.length === 1 ? 'One source explains' : `${sources.length} sources explain`} much of the rest.</>}</>

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-6 pb-14 pt-5 lg:px-9">
      <PageHeader title={headline}
        lead={repaired
          ? 'Every change is recorded with its evidence and can be undone. Suggestions DataFix was less sure about wait in the Repair Studio.'
          : 'Nothing changes until you apply a repair. DataFix proposes a fix for each problem, backed by evidence and a confidence score, or refuses when the evidence is not there.'}
        actions={<Link to={`/s/${sid}/diagnosis`}><Button><Search className="size-4" />Full diagnosis</Button></Link>} />

      <div className="grid grid-cols-2 gap-4 pt-2 lg:grid-cols-4">
        <Kpi label="Clean rows" tone="green" value={pct(d1?.clean_rows ?? d0.clean_rows)}
          hint={d1 ? <>was {pct(d0.clean_rows)} · rows with no problem at all</> : 'Rows with no problem at all'} />
        <Kpi label="Missing" value={num(missing)} tone="red"
          hint={`${num(c.disguised_missing)} are placeholders`} onClick={() => open('Missing values', { issue_type: 'missing' })} />
        <Kpi label="Duplicates" value={num(dups)} tone="amber"
          hint={`${num(c.near_duplicate)} are near-duplicates`} onClick={() => open('Duplicate rows', { issue_type: 'duplicate' })} />
        <Kpi label="Invalid" value={num(c.invalid_format)} tone="red" hint="Fail a format or range check"
          onClick={() => open('Invalid values', { issue_type: 'invalid_format' })} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <NextStep s={s} sid={sid} />
        <Card title="Problems by type" subtitle={<>{num(s.rows)} rows{s.linked_tables.map((t) => ` + ${num(t.rows)} ${t.name}`).join('')} · click a type to see the rows</>}>
          <Donut slices={[
            { label: 'Missing', value: missing, color: '#1D4D4F', onClick: () => open('Missing values', { issue_type: 'missing' }) },
            { label: 'Inconsistent', value: c.inconsistent ?? 0, color: '#B7812B', onClick: () => open('Inconsistent values', { issue_type: 'inconsistent' }) },
            { label: 'Invalid', value: c.invalid_format ?? 0, color: '#B4442F', onClick: () => open('Invalid values', { issue_type: 'invalid_format' }) },
            { label: 'Duplicates', value: dups, color: '#3E7B58', onClick: () => open('Duplicate rows', { issue_type: 'duplicate' }) },
            { label: 'Rule violations', value: (c.fd_violation ?? 0) + (c.crossfield ?? 0), color: '#8C8476', onClick: () => open('Rule violations', { issue_type: 'fd_violation' }) },
            { label: 'Unusual values', value: c.anomaly ?? 0, color: '#CFC6B4', onClick: () => open('Unusual values', { issue_type: 'anomaly' }) },
          ]} />
          {(s.pii_columns ?? 0) > 0 && (
            <Link to={`/s/${sid}/privacy`} className="mt-4 flex items-center gap-2 rounded-xl bg-slate-50 px-3.5 py-2.5 text-[13px] hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-800">
              <ShieldAlert className="size-4 text-rose-500" /><span><b>{num(s.pii_columns)} columns hold personal data.</b> Review masking on the Privacy page.</span>
              <ArrowRight className="ml-auto size-4 text-slate-400" />
            </Link>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card title="Clean rows" subtitle={repaired ? 'Estimate; Validation re-checks everything' : 'Share of rows with no problem at all'}>
          <div className="flex justify-center pt-1"><ScoreGauge before={d0.clean_rows} after={d1?.clean_rows} /></div>
        </Card>
        <Card title="Quality by dimension" subtitle="Share of rows without the problem">
          <DimensionBars before={d0} after={d1} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Smart warnings" subtitle="Highest-impact issues first"
          action={<span className="flex items-center gap-2"><Badge>{num(ws.length)} total</Badge>{ws.length > 6 && <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : 'Show all'}</Button>}</span>}>
          {warnings.isLoading ? <Skeleton className="h-48" /> : ws.length === 0 ? <EmptyState title="No problems found" /> : (
            <ul className="-my-3.5 divide-y divide-slate-200 dark:divide-slate-800">
              {(showAll ? ws : ws.slice(0, 6)).map((w) => (
                <WarningRow key={w.warning_id} w={w} onShow={() => open(w.title,
                  w.issue_type === 'duplicate' || w.issue_type === 'near_duplicate'
                    ? { issue_type: w.issue_type } : { issue_type: w.issue_type, column: w.column ?? undefined }, w.column ?? undefined)} />
              ))}
            </ul>
          )}
        </Card>
        <Card title="Why the data is dirty" subtitle="Grouped by where the errors come from"
          action={<Link to={`/s/${sid}/diagnosis`} className="whitespace-nowrap text-sm font-medium text-brand-600 hover:underline dark:text-brand-300">Full diagnosis</Link>}>
          {diag.isLoading ? <Skeleton className="h-40" /> : (
            <ul className="-mt-1 divide-y divide-slate-200 dark:divide-slate-800">
              {sources.slice(0, 3).map((x) => (
                <li key={x.cause_id} className="py-3.5 first:pt-1">
                  <div className="font-semibold">{x.title}</div>
                  <div className="mt-1 text-[13px] leading-snug text-slate-500">{x.suggested_fix}</div>
                </li>
              ))}
              <li className="pt-3.5"><Link to={`/s/${sid}/diagnosis`} className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline">
                See all causes and the rules DataFix learned <ArrowRight className="size-3.5" /></Link></li>
            </ul>
          )}
        </Card>
      </div>

      <Card title="Where the errors are" subtitle="Columns × blocks of rows. Darker means more problems; click a cell to see its rows">
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
