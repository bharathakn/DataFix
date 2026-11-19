import { ChevronLeft, ChevronRight, Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { useRows, useSession } from '../api/hooks'
import { cn, maskSample, num } from '../lib/format'
import { Button, ErrorNote, Legend, Skeleton } from './ui'

export interface GridFilter {
  view?: 'current' | 'original' | 'diff'
  issue_type?: string
  column?: string
  state?: string
  row_ids?: string
}

const PAGE = 50
const PII_TYPES = new Set(['phone', 'email', 'aadhaar', 'pan', 'gstin', 'ifsc', 'text'])

/** Paged table of rows with per-cell state colours; hover a repaired cell to see its before-value. */
export function DataGrid({ sid, filter, highlightColumn, onRowClick }:
  { sid: string; filter: GridFilter; highlightColumn?: string; onRowClick?: (rowId: number) => void }) {
  const [page, setPage] = useState(0)
  const [reveal, setReveal] = useState(false)
  const q = { ...filter, offset: page * PAGE, limit: PAGE }
  const { data, isLoading, error } = useRows(sid, q)
  const { data: session } = useSession(sid)
  const types = Object.fromEntries((session?.columns ?? []).map((c) => [c.name, c.semantic_type]))
  const show = (col: string, v: string) => (!reveal && PII_TYPES.has(types[col]) ? maskSample(v, types[col]) : v)
  if (error) return <ErrorNote error={error} />
  if (isLoading || !data) return <div className="space-y-2">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-7" />)}</div>
  const pages = Math.max(1, Math.ceil(data.total / PAGE))
  // the column the user came for goes first
  const columns = highlightColumn && data.columns.includes(highlightColumn)
    ? [highlightColumn, ...data.columns.filter((c) => c !== highlightColumn)] : data.columns
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend />
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Button variant="ghost" className="text-xs" onClick={() => setReveal(!reveal)} title="Phone, email, ID numbers and notes are masked by default">
            {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}{reveal ? 'Hide personal data' : 'Show personal data'}
          </Button>
          <span className="tabular">{num(data.total)} rows</span>
          <Button variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
          <span className="tabular">{page + 1} / {pages}</span>
          <Button variant="ghost" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight className="size-4" /></Button>
        </div>
      </div>
      <div className="overflow-auto rounded-lg border border-slate-200 dark:border-slate-800" style={{ maxHeight: '65vh' }}>
        <table className="min-w-full text-xs">
          <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800">
            <tr>
              <th className="sticky left-0 bg-slate-100 px-2 py-2 text-left font-semibold text-slate-500 dark:bg-slate-800">row</th>
              {columns.map((c) => (
                <th key={c} className={cn('whitespace-nowrap px-2 py-2 text-left font-semibold',
                  c === highlightColumn ? 'text-brand-700 dark:text-brand-100' : 'text-slate-600 dark:text-slate-300')}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.row_id} onClick={() => onRowClick?.(r.row_id)}
                className={cn('border-t border-slate-100 dark:border-slate-800', onRowClick && 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50')}>
                <td className="tabular sticky left-0 bg-white px-2 py-1.5 text-slate-400 dark:bg-slate-900">{r.row_id}</td>
                {columns.map((c) => {
                  const st = r.cell_state[c]
                  const before = r.original[c]
                  return (
                    <td key={c} title={before !== undefined ? `was: ${show(c, before) || '(blank)'}` : st ? st : undefined}
                      className={cn('max-w-[220px] truncate whitespace-nowrap px-2 py-1.5', st && `cell-${st}`,
                        c === highlightColumn && !st && 'bg-brand-50/60 dark:bg-brand-700/10')}>
                      {r.values[c] === '' ? <span className="text-slate-400 italic">blank</span> : show(c, r.values[c])}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {data.rows.length === 0 && <div className="p-6 text-center text-sm text-slate-500">No rows match.</div>}
      </div>
    </div>
  )
}
