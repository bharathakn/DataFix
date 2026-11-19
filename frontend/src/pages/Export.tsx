import { AlertTriangle, CheckCircle2, Download, FileCode2, FileJson, FileSpreadsheet, FileText, Lock, Package, ScrollText } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useSession, useValidation } from '../api/hooks'
import { Badge, Button, Card, ErrorNote, Skeleton, Spinner } from '../components/ui'
import { num, pct } from '../lib/format'

const FILES = [
  { kind: 'cleaned_csv', name: 'cleaned_data.csv', icon: FileSpreadsheet, desc: 'Same columns and order as your upload, plus a _datafix_status column (unchanged / repaired / estimated / needs_review).' },
  { kind: 'highlighted_xlsx', name: 'cleaned_highlighted.xlsx', icon: FileSpreadsheet, desc: 'Excel copy: repaired cells green, estimates blue, review items yellow, masked purple. Hover notes give the before value, reason and confidence (up to 3,000 cells, open review items first).' },
  { kind: 'report_html', name: 'quality_report.html', icon: FileText, desc: 'Readable report: quality before → after, root causes, repairs by method, do-no-harm checks, benchmark, privacy, open items, audit trail. Print to PDF from the browser.' },
  { kind: 'change_log_csv', name: 'change_log.csv', icon: ScrollText, desc: 'Every change, undo and rejection with before / after, reason, evidence, source, confidence and the hash chain.' },
  { kind: 'privacy_csv', name: 'privacy_report.csv', icon: Lock, desc: 'Personal data found per column, how it was confirmed, and how it was masked.' },
  { kind: 'recipe_json', name: 'cleaning_recipe.json', icon: FileJson, desc: 'The approved steps as data (column types, value maps, rules, thresholds) to re-clean next month\'s file the same way.' },
]

export default function Export() {
  const { sid = '' } = useParams()
  const { data: s } = useSession(sid)
  const planned = !!s && (s.stage === 'planned' || s.stage === 'repairing')
  const v = useValidation(sid, planned)
  const [preview, setPreview] = useState(false)
  const [frameReady, setFrameReady] = useState(false)
  const [zipping, setZipping] = useState(false)
  const [zipError, setZipError] = useState<Error | null>(null)
  // fetch instead of a plain link: one request at a time, a visible "Preparing…" state, and errors shown here
  const downloadZip = async () => {
    setZipping(true)
    setZipError(null)
    try {
      const r = await fetch(api.exportUrl(sid, 'zip'))
      if (!r.ok) throw new Error(`Export failed (${r.status})`)
      const url = URL.createObjectURL(await r.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = 'datafix_output.zip'
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (e) {
      setZipError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      setZipping(false)
    }
  }
  if (!s) return <div className="p-6"><Skeleton className="h-96" /></div>
  if (s.stage === 'loaded') return <Navigate to={`/s/${sid}/setup`} replace />
  if (!planned) return <Navigate to={`/s/${sid}`} replace />
  const val = v.data
  const failed = val?.checks.filter((c) => !c.passed) ?? []
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Export</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">Your original upload is never changed. Everything below is generated from the current checkpoint.</p>
        </div>
        <div className="text-right">
          <Button variant="primary" loading={zipping} onClick={downloadZip}>
            {!zipping && <Package className="size-4" />}{zipping ? 'Preparing ZIP…' : 'Download all (ZIP)'}
          </Button>
          {zipping && <p className="mt-1 text-xs text-slate-500">Building 7 files; about 15 s for 30k rows.</p>}
        </div>
      </div>
      <ErrorNote error={zipError} />

      <Card>
        {v.isLoading ? <Spinner label="Checking the repaired data before export…" /> : val && (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
            <div className="flex items-center gap-2">
              {failed.length ? <AlertTriangle className="size-5 text-rose-600" /> : <CheckCircle2 className="size-5 text-emerald-600" />}
              <span className="font-medium">{failed.length ? `${failed.length} do-no-harm check(s) failed` : 'All 8 do-no-harm checks passed'}</span>
            </div>
            <div className="text-sm"><span className="text-slate-500">Clean rows</span> <b className="tabular">{pct(val.dimensions_before.clean_rows)} → {pct(val.dimensions_after.clean_rows)}</b></div>
            <div className="text-sm"><span className="text-slate-500">Rows</span> <b className="tabular">{num(s.rows)} → {num(s.rows_current)}</b></div>
            <div className="flex gap-2 text-sm">
              <Badge tone="amber">{num(val.unresolved.review)} need review</Badge>
              <Badge tone="red">{num(val.unresolved.refused)} refused</Badge>
              <Badge>{num(val.unresolved.flag)} flagged</Badge>
            </div>
            {failed.length > 0 && <Link to={`/s/${sid}/validation`} className="text-sm text-brand-600 underline">See validation</Link>}
          </div>
        )}
        {val && val.unresolved.review > 0 && (
          <p className="mt-3 text-xs text-slate-500">Open review items are exported unchanged and marked <code>needs_review</code>; you can still decide them in the <Link className="underline" to={`/s/${sid}/repair`}>Repair Studio</Link> and export again.</p>
        )}
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        {FILES.map((f) => (
          <Card key={f.kind}>
            <div className="flex gap-3">
              <f.icon className="mt-0.5 size-5 shrink-0 text-brand-600" />
              <div className="min-w-0 flex-1">
                <div className="font-mono text-sm font-semibold">{f.name}</div>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{f.desc}</p>
              </div>
              <a href={api.exportUrl(sid, f.kind)} download={f.name} aria-label={`Download ${f.name}`}>
                <Button variant="ghost"><Download className="size-4" /></Button>
              </a>
            </div>
          </Card>
        ))}
      </div>

      <Card title={<span className="flex items-center gap-2"><FileCode2 className="size-4" />Quality report preview</span>}
        action={<Button variant="ghost" className="text-xs" onClick={() => { setPreview(!preview); setFrameReady(false) }}>{preview ? 'Hide' : 'Show preview'}</Button>}>
        {preview ? (
          <div className="relative">
            {!frameReady && <div className="absolute inset-0 flex items-center justify-center"><Spinner label="Generating the report…" /></div>}
            <iframe title="Quality report" src={api.exportUrl(sid, 'report_html') + '?inline=1'} onLoad={() => setFrameReady(true)}
              className="h-[70vh] w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800" />
          </div>
        )
          : <p className="text-sm text-slate-500">Generates the report from the current state (a few seconds).</p>}
      </Card>
    </div>
  )
}
