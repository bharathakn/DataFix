import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, FlaskConical, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { keys, useSession, useSessionMutation, useValidation } from '../api/hooks'
import type { BenchmarkResult, Check } from '../api/types'
import { Badge, Button, Card, ErrorNote, Kpi, Skeleton, Spinner } from '../components/ui'
import { cn, DIMENSION_LABELS, num, pct } from '../lib/format'

const CHECKS: Record<string, { title: string; plain: string }> = {
  valid_cells_changed: { title: 'No valid value was changed', plain: 'Every edited cell had a detected problem.' },
  schema_unchanged: { title: 'Schema unchanged', plain: 'Same columns, same order as the upload.' },
  row_count_explained: { title: 'Every removed row is explained', plain: 'Rows only disappear through approved duplicate merges.' },
  distribution_stable: { title: 'Distributions stable', plain: 'Medians, spreads and category shares barely moved.' },
  no_new_errors: { title: 'No new errors introduced', plain: 'Re-scanning the repaired data finds nothing wrong in any cell DataFix touched.' },
  referential_integrity: { title: 'Relationships intact', plain: 'Every linked order still points to an existing customer.' },
  idempotent: { title: 'Stable: nothing more to auto-fix', plain: 'Running DataFix again on its own output proposes no further automatic changes.' },
  audit_chain_valid: { title: 'Audit log is tamper-evident and intact', plain: 'The hash chain from the input file to the last change verifies.' },
}

function CheckRow({ c }: { c: Check }) {
  const meta = CHECKS[c.name] ?? { title: c.name, plain: '' }
  return (
    <li className="flex gap-3 py-3">
      {c.passed ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 size-5 shrink-0 text-rose-600" />}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="font-medium">{meta.title}</span>
          <span className="tabular text-sm font-semibold">{c.value}</span>
        </div>
        <div className="text-sm text-slate-600 dark:text-slate-400">{meta.plain}</div>
        <div className="mt-0.5 text-xs text-slate-500" title={c.detail}>{c.detail}</div>
      </div>
    </li>
  )
}

const BENCH_STEPS = ['Taking rows with no problems as ground truth', 'Planting known errors and duplicates',
  'Running detection and repair end to end', 'Scoring every cell against the truth']

function BenchProgress() {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((x) => Math.min(x + 1, BENCH_STEPS.length - 1)), 1200)
    return () => clearInterval(t)
  }, [])
  return <Spinner label={BENCH_STEPS[i] + '…'} />
}

function Calibration({ data }: { data: BenchmarkResult['calibration'] }) {
  if (!data.length) return null
  const w = 360, h = 150, pad = 28, bw = (w - pad) / data.length
  return (
    <div>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Calibration: predicted confidence vs actual accuracy</div>
      <svg viewBox={`0 0 ${w} ${h + 30}`} className="w-full max-w-md" role="img" aria-label="Calibration chart">
        {[0, 0.5, 1].map((y) => (
          <g key={y}>
            <line x1={pad} x2={w} y1={h - y * h + 4} y2={h - y * h + 4} className="stroke-slate-200 dark:stroke-slate-800" />
            <text x={pad - 4} y={h - y * h + 8} textAnchor="end" className="fill-slate-400 text-[9px]">{y * 100}%</text>
          </g>
        ))}
        {data.map((b, i) => {
          const x = pad + i * bw + bw * 0.15, bar = bw * 0.33
          return (
            <g key={b.bucket}>
              <rect x={x} y={h - b.predicted * h + 4} width={bar} height={b.predicted * h} className="fill-slate-300 dark:fill-slate-600" />
              <rect x={x + bar + 2} y={h - b.actual * h + 4} width={bar} height={b.actual * h} className="fill-emerald-500" />
              <text x={x + bar} y={h + 18} textAnchor="middle" className="fill-slate-500 text-[9px]">{b.bucket}</text>
              <text x={x + bar} y={h + 28} textAnchor="middle" className="fill-slate-400 text-[8px]">n={b.n}</text>
            </g>
          )
        })}
      </svg>
      <div className="flex gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1"><span className="size-2.5 bg-slate-300 dark:bg-slate-600" />predicted</span>
        <span className="flex items-center gap-1"><span className="size-2.5 bg-emerald-500" />actually correct</span>
      </div>
    </div>
  )
}

function BenchmarkPanel({ sid }: { sid: string }) {
  const qc = useQueryClient()
  const [rows, setRows] = useState(2000)
  const [seed, setSeed] = useState(42)
  const last = useQuery({ queryKey: [sid, 'benchmark'], queryFn: () => api.lastBenchmark(sid) })
  const run = useSessionMutation(sid, () => api.benchmark(sid, { sample_rows: rows, seed }))
  const r = run.data ?? last.data
  useEffect(() => { if (run.data) qc.setQueryData([sid, 'benchmark'], run.data) }, [run.data, qc, sid])
  return (
    <Card title={<span className="flex items-center gap-2"><FlaskConical className="size-4" />Self-test benchmark</span>}
      action={<div className="flex items-center gap-2 text-xs">
        <label className="flex items-center gap-1">rows
          <select value={rows} onChange={(e) => setRows(Number(e.target.value))} className="rounded border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900">
            {[1000, 2000, 5000].map((n) => <option key={n} value={n}>{num(n)}</option>)}
          </select></label>
        <label className="flex items-center gap-1">seed
          <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)}
            className="w-16 rounded border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900" /></label>
        <Button variant="primary" className="text-xs" loading={run.isPending} onClick={() => run.mutate(undefined)}>Run benchmark</Button>
      </div>}>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Proof on <b>your own data</b>: DataFix takes rows that had no problems, plants known errors in them (blanks, typos,
        broken PINs and phones, US dates, duplicates…), repairs them as if a reviewer accepted every suggestion, and scores
        every cell against the truth. The headline number is the <b>false repair rate</b>: how many correct values it damaged.
      </p>
      <ErrorNote error={run.error} />
      {run.isPending && <div className="mt-4"><BenchProgress /></div>}
      {!r && !run.isPending && <div className="mt-4 text-sm text-slate-500">Not run yet for this session.</div>}
      {r && !run.isPending && (
        <div className="mt-4 space-y-5">
          <div className="text-xs text-slate-500">{r.injected} errors planted in {num(r.sample_rows)} clean rows · seed {r.seed} · {(r.duration_ms / 1000).toFixed(1)} s</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Kpi label="False repair rate" value={pct(r.repair.false_repair_rate * 100, 3)} tone={r.repair.false_repair_rate <= 0.005 ? 'green' : 'red'}
              hint={`${r.repair.false_repairs} valid cells changed`} />
            <Kpi label="Repair precision" value={pct(r.repair.precision * 100)} tone="green" hint={`${r.repair.correct} right · ${r.repair.wrong} wrong`} />
            <Kpi label="Detection F1" value={r.detection.f1.toFixed(3)} hint={`P ${pct(r.detection.precision * 100)} · R ${pct(r.detection.recall * 100)}`} />
            <Kpi label="Coverage" value={pct(r.repair.coverage * 100)} hint="errors that got a repair" />
            <Kpi label="Auto-tier precision" value={pct(r.repair.auto_precision * 100)} hint="applied without review" />
            <Kpi label="Estimates" value={num(r.repair.estimates)} hint={r.repair.estimate_mean_abs_error !== null ? `mean error ±${r.repair.estimate_mean_abs_error}` : 'group medians'} />
          </div>
          <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Planted error</th><th className="text-right">Planted</th><th className="text-right">Detected</th><th className="text-right">Repaired correctly</th></tr></thead>
              <tbody>
                {r.by_error_type.map((t) => (
                  <tr key={t.type} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">{t.type.replace(/_/g, ' ')}</td>
                    <td className="tabular text-right">{t.injected}</td>
                    <td className={cn('tabular text-right', t.detected < t.injected && 'text-amber-600')}>{t.detected}</td>
                    <td className="tabular text-right">{t.repaired_correctly}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Calibration data={r.calibration} />
          </div>
          <p className="text-xs text-slate-500">
            Unrepaired errors are mostly blanks with no evidence anywhere (DataFix refuses to invent them) and estimates
            that wait for review. These are planted error types; real files will score lower, which is why the benchmark runs on any upload.
          </p>
        </div>
      )}
    </Card>
  )
}

export default function Validation() {
  const { sid = '' } = useParams()
  const qc = useQueryClient()
  const { data: s } = useSession(sid)
  const planned = !!s && (s.stage === 'planned' || s.stage === 'repairing')
  const v = useValidation(sid, planned)
  if (!s) return <div className="p-6"><Skeleton className="h-96" /></div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />
  const val = v.data
  return (
    <div className="mx-auto max-w-7xl space-y-5 px-6 pb-14 pt-5 lg:px-9">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[34px] leading-[1.12] text-slate-900 dark:text-slate-50">Validation: prove it</h1>
          <p className="mt-2.5 max-w-3xl text-[14.5px] leading-relaxed text-slate-500 dark:text-slate-400">DataFix re-scans the repaired data from scratch and checks that the repairs did no harm.</p>
        </div>
        {planned && <Button onClick={() => qc.invalidateQueries({ queryKey: keys.validation(sid) })} loading={v.isFetching}>
          <RefreshCw className="size-4" />Re-run checks</Button>}
      </div>

      {!planned ? (
        <Card><div className="text-sm">Plan repairs on the <Link className="text-brand-600 underline" to={`/s/${sid}`}>Overview</Link> first; the benchmark below already works.</div></Card>
      ) : v.isLoading ? (
        <Card><Spinner label="Re-scanning the repaired data and re-planning on DataFix's own output (≈ 5 s)…" /></Card>
      ) : v.error ? <ErrorNote error={v.error} /> : val && (
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <Card title={<span className="flex items-center gap-2"><ShieldCheck className="size-4" />Do-no-harm checks</span>}
            action={<Badge tone={val.passed ? 'green' : 'red'}>{val.checks.filter((c) => c.passed).length} / {val.checks.length} passed</Badge>}>
            <ul className="-my-3 divide-y divide-slate-100 dark:divide-slate-800">{val.checks.map((c) => <CheckRow key={c.name} c={c} />)}</ul>
          </Card>
          <div className="space-y-5">
            <Card title="Before → after (full re-scan)">
              <div className="mb-4 flex items-end gap-6">
                <div><div className="text-xs uppercase tracking-wide text-slate-500">Clean rows</div>
                  <div className="tabular text-3xl font-semibold"><span className="text-rose-500">{pct(val.dimensions_before.clean_rows)}</span> → <span className="text-emerald-600">{pct(val.dimensions_after.clean_rows)}</span></div></div>
                <div><div className="text-xs uppercase tracking-wide text-slate-500">Score</div>
                  <div className="tabular text-lg font-semibold">{val.score_before} → {val.score_after}</div></div>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {(['completeness', 'validity', 'consistency', 'uniqueness'] as const).map((d) => (
                    <tr key={d} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1.5">{DIMENSION_LABELS[d]}</td>
                      <td className="tabular text-right text-slate-500">{pct(val.dimensions_before[d])}</td>
                      <td className="tabular w-20 text-right font-semibold text-emerald-600">{pct(val.dimensions_after[d])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Still open">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div><div className="tabular text-xl font-semibold text-amber-600">{num(val.unresolved.review)}</div><div className="text-xs text-slate-500">need review</div></div>
                <div><div className="tabular text-xl font-semibold text-rose-600">{num(val.unresolved.refused)}</div><div className="text-xs text-slate-500">refused</div></div>
                <div><div className="tabular text-xl font-semibold">{num(val.unresolved.flag)}</div><div className="text-xs text-slate-500">flagged</div></div>
              </div>
              <p className="mt-3 text-xs text-slate-500">
                {num(val.remaining_errors)} problems remain in the data;{' '}
                {val.checks.find((c) => c.name === 'no_new_errors')?.passed ? 'none of them was created by a repair' : 'some were introduced by repairs (see the failed check)'}
                {val.surfaced > 0 && ` (${val.surfaced} surfaced only after neighbouring errors were fixed)`}. Checked in {(val.duration_ms / 1000).toFixed(1)} s.</p>
            </Card>
          </div>
        </div>
      )}

      <BenchmarkPanel sid={sid} />
    </div>
  )
}
