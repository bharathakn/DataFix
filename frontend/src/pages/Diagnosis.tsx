import { useMutation, useQuery } from '@tanstack/react-query'
import { BrainCircuit, GitBranch, Lightbulb, Sparkles, Wrench } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useDiagnosis, useSession } from '../api/hooks'
import type { RootCause } from '../api/types'
import { DataGrid, type GridFilter } from '../components/DataGrid'
import { Badge, Button, Card, Drawer, EmptyState, ErrorNote, Skeleton } from '../components/ui'
import { cn, num, pct } from '../lib/format'

const KIND_TO_ISSUE: Record<string, string> = {
  placeholder: 'disguised_missing', truncation: 'invalid_format', excel_scientific_notation: 'invalid_format',
  encoding: 'invalid_format', date_format: 'inconsistent', money_format: 'inconsistent', whitespace: 'inconsistent', case: 'inconsistent',
}

function GroupBars({ c }: { c: RootCause }) {
  const max = Math.max(...c.rate_by_group.map((g) => g.rate), 0.0001)
  const culprit = c.group?.value
  return (
    <div className="space-y-1">
      {c.rate_by_group.map((g) => (
        <div key={g.value} className="flex items-center gap-2 text-xs">
          <span className={cn('w-40 shrink-0 truncate text-right', g.value === culprit ? 'font-semibold' : 'text-slate-500')} title={g.value}>{g.value}</span>
          <div className="h-3 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
            <div className={cn('h-full rounded', g.value === culprit ? 'bg-rose-500' : 'bg-slate-300 dark:bg-slate-600')}
              style={{ width: `${Math.max(1, (g.rate / max) * 100)}%` }} />
          </div>
          <span className="tabular w-28 shrink-0 text-slate-500">{pct(g.rate * 100)} · {g.issues}/{num(g.rows)}</span>
        </div>
      ))}
      <div className="pl-[10.5rem] text-[11px] text-slate-400">share of rows in each group with this problem</div>
    </div>
  )
}

function CauseCard({ c, onShow }: { c: RootCause; onShow: () => void }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="font-mono">{c.cause_id}</span>
            {c.kind === 'source_lift' && <Badge tone="red">{c.times_elsewhere ? `${c.times_elsewhere.toLocaleString()}× more likely than elsewhere` : 'only in this group'}</Badge>}
            {c.share_of_issues !== null && <Badge>{pct(c.share_of_issues * 100, 0)} of these errors</Badge>}
          </div>
          <h3 className="mt-1 text-base font-semibold">{c.title}</h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{c.explanation}</p>
          <p className="mt-2 flex gap-1.5 text-sm"><Wrench className="mt-0.5 size-4 shrink-0 text-brand-600" /><span><b>Fix at the source:</b> {c.suggested_fix}</span></p>
        </div>
        <Button variant="ghost" className="text-xs" onClick={onShow}>Show rows</Button>
      </div>
      {c.rate_by_group.length > 1 && <div className="mt-4"><GroupBars c={c} /></div>}
    </Card>
  )
}

export default function Diagnosis() {
  const { sid = '' } = useParams()
  const { data: s } = useSession(sid)
  const diag = useDiagnosis(sid, s?.stage)
  const rules = useQuery({ queryKey: [sid, 'rules'], queryFn: () => api.rules(sid), enabled: !!s && s.stage !== 'loaded' })
  const ai = useMutation({ mutationFn: () => api.diagnosis(sid, true) })
  const [grid, setGrid] = useState<{ title: string; filter: GridFilter; column?: string } | null>(null)

  if (!s) return <div className="p-6"><Skeleton className="h-96" /></div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />
  const causes = diag.data?.causes ?? []
  const source = causes.filter((c) => c.kind === 'source_lift')
  const patterns = causes.filter((c) => c.kind === 'pattern')
  const template = source.slice(0, 3).map((c) => c.title + '.').join(' ')
  const show = (c: RootCause) => {
    const issue = c.kind === 'pattern' ? KIND_TO_ISSUE[c.issue_type] : c.issue_type
    const column = c.column?.includes(',') ? undefined : c.column ?? undefined
    setGrid({ title: c.title, filter: { issue_type: issue, column }, column })
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Diagnosis: why the data is dirty</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          DataFix groups errors by where they came from (source, batch, month) and by the mechanism that made them, so you can fix the pipeline, not just the rows.
        </p>
      </div>

      <Card title={<span className="flex items-center gap-2"><BrainCircuit className="size-4" />Summary</span>}
        action={!ai.data && <Button variant="ghost" className="text-xs" loading={ai.isPending} onClick={() => ai.mutate()}><Sparkles className="size-4" />Summarise with AI</Button>}>
        {diag.isLoading ? <Skeleton className="h-12" /> : (
          <p className="text-[15px] leading-relaxed">
            {ai.data?.narrative ?? (template || 'No concentrated source of errors found: problems are spread evenly.')}
            {ai.data && <span className="ml-2 text-xs text-slate-500">({ai.data.mode === 'gemini' ? 'written by Gemini from the findings below' : 'AI unavailable: template'})</span>}
          </p>
        )}
        <ErrorNote error={ai.error} />
      </Card>

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 font-semibold"><GitBranch className="size-4" />Where the errors come from ({source.length})</h2>
        {diag.isLoading ? <Skeleton className="h-48" /> : source.length === 0
          ? <Card><EmptyState title="No source concentrates the errors">Either the file has no source/batch column, or errors are spread evenly.</EmptyState></Card>
          : <div className="grid gap-4 lg:grid-cols-2">{source.map((c) => <CauseCard key={c.cause_id} c={c} onShow={() => show(c)} />)}</div>}
      </section>

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 font-semibold"><Lightbulb className="size-4" />How the errors were made ({patterns.length})</h2>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {patterns.map((c) => (
            <button key={c.cause_id} onClick={() => show(c)} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-brand-500 dark:border-slate-800 dark:bg-slate-900">
              <div className="font-semibold">{c.title.split(':')[0]}</div>
              <div className="tabular text-xs text-slate-500">{c.title.split(':').slice(1).join(':')}</div>
              <div className="mt-2 text-sm text-slate-600 dark:text-slate-400">{c.explanation}</div>
              <div className="mt-2 text-xs"><b>Fix:</b> {c.suggested_fix}</div>
            </button>
          ))}
        </div>
      </section>

      <Card title="Rules DataFix learned from your data" action={<span className="text-xs text-slate-500">nobody wrote these; they were discovered from the data</span>}>
        {rules.isLoading ? <Skeleton className="h-32" /> : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr><th className="py-1.5">Rule</th><th className="text-right">Rows supporting</th><th className="text-right">Holds in</th><th className="text-right">Violations found</th><th className="pl-4">Kind</th></tr>
            </thead>
            <tbody>
              {(rules.data ?? []).map((r) => (
                <tr key={r.rule_id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5"><span className="font-mono">{r.lhs}</span> → <span className="font-mono">{r.rhs}</span>
                    <span className="ml-2 text-xs text-slate-500">{r.description}</span></td>
                  <td className="tabular text-right">{num(r.support)}</td>
                  <td className="tabular text-right">{pct(r.confidence * 100)}</td>
                  <td className="tabular text-right">
                    {r.violations > 0 ? <button className="font-semibold text-rose-600 hover:underline"
                      onClick={() => setGrid({ title: `Rows breaking: ${r.description}`, filter: { issue_type: r.kind === 'fd' ? 'fd_violation' : 'crossfield', column: r.rhs.split(',')[0] }, column: r.rhs })}>{r.violations}</button> : 0}
                  </td>
                  <td className="pl-4"><Badge tone={r.kind === 'fd' ? 'blue' : 'violet'}>{r.kind === 'fd' ? 'learned dependency' : 'cross-field'}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Drawer open={!!grid} onClose={() => setGrid(null)} title={grid?.title} wide>
        {grid && <DataGrid key={JSON.stringify(grid.filter)} sid={sid} filter={grid.filter} highlightColumn={grid.column} />}
      </Drawer>
    </div>
  )
}
