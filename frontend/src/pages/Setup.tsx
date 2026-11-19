import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, ScanSearch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useSession } from '../api/hooks'
import type { ColumnInfo } from '../api/types'
import { Badge, Button, Card, ErrorNote, Skeleton } from '../components/ui'
import { cn, maskSample, num, OVERRIDABLE_TYPES, TYPE_LABELS } from '../lib/format'

const STEPS = ['Reading every value as text', 'Detecting missing, invalid and inconsistent values',
  'Learning rules from the data', 'Finding duplicates and outliers', 'Diagnosing root causes', 'Scanning for personal data']

function ScanProgress() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1100)
    return () => clearInterval(t)
  }, [])
  return (
    <ol className="space-y-2">
      {STEPS.map((s, i) => (
        <li key={s} className={cn('flex items-center gap-2 text-sm', i > step && 'text-slate-400')}>
          {i < step ? <Check className="size-4 text-emerald-600" />
            : i === step ? <span className="size-4 animate-pulse rounded-full bg-brand-500" />
              : <span className="size-4 rounded-full border border-slate-300" />}
          {s}
        </li>
      ))}
    </ol>
  )
}

function ColumnCard({ c, value, onChange }: { c: ColumnInfo; value: string; onChange: (t: string) => void }) {
  const changed = value !== c.semantic_type
  return (
    <div className={cn('min-w-0 rounded-[14px] border bg-white p-4 dark:bg-slate-900', changed ? 'border-brand-500 ring-1 ring-brand-500/30' : 'border-slate-200 dark:border-slate-800')}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm font-semibold" title={c.name}>{c.name}</div>
          <div className="mt-1 text-xs text-slate-500">{num(c.distinct)} distinct · {num(c.null_count)} blank</div>
        </div>
        {changed ? <Badge tone="blue">changed</Badge> : c.type_confidence < 0.8 && <Badge tone="amber">check</Badge>}
      </div>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={`Type of ${c.name}`}
        className="mt-3 w-full rounded-[9px] border border-slate-300 bg-white px-2.5 py-2 text-sm dark:border-slate-700 dark:bg-slate-800">
        {OVERRIDABLE_TYPES.map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
      </select>
      <div className="mt-3 space-y-0.5 rounded-[9px] bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
        {c.sample.slice(0, 3).map((x, i) => (
          <div key={i} className="truncate font-mono text-xs leading-relaxed text-slate-600 dark:text-slate-300" title="sample value (personal data masked)">
            {maskSample(x, value) || <i>blank</i>}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Setup() {
  const { sid = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: s, error } = useSession(sid)
  const [types, setTypes] = useState<Record<string, string>>({})
  const scan = useMutation({
    mutationFn: () => {
      const overrides = Object.fromEntries(
        Object.entries(types).filter(([col, t]) => s?.columns.find((c) => c.name === col)?.semantic_type !== t))
      return api.scan(sid, overrides)
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: [sid] })
      nav(`/s/${sid}`)
    },
  })
  if (error) return <div className="p-6"><ErrorNote error={error} /></div>
  if (!s) return <div className="grid gap-3 p-6 sm:grid-cols-3">{Array.from({ length: 9 }, (_, i) => <Skeleton key={i} className="h-32" />)}</div>
  const scanned = s.stage !== 'loaded'
  return (
    <div className="mx-auto max-w-7xl space-y-6 px-6 pb-14 pt-5 lg:px-9">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[34px] leading-[1.12] text-slate-900 dark:text-slate-50">Check the column types</h1>
          <p className="mt-2.5 max-w-3xl text-[14.5px] leading-relaxed text-slate-500 dark:text-slate-400">
            DataFix recognised each column from its values, not just its name. Correct anything that looks wrong, then scan.
          </p>
        </div>
        {scanned
          ? <Link to={`/s/${sid}`}><Button variant="primary">Already scanned · go to overview</Button></Link>
          : <Button variant="primary" loading={scan.isPending} onClick={() => scan.mutate()}><ScanSearch className="size-4" />Scan {num(s.rows)} rows</Button>}
      </div>
      <ErrorNote error={scan.error} />
      {scan.isPending && <Card title="Scanning…"><ScanProgress /></Card>}
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {s.columns.map((c) => (
          <ColumnCard key={c.name} c={c} value={types[c.name] ?? c.semantic_type}
            onChange={(t) => setTypes({ ...types, [c.name]: t })} />
        ))}
      </div>
    </div>
  )
}
