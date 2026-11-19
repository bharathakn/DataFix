import { useState } from 'react'
import type { Dimensions, Heatmap as HeatmapData } from '../api/types'
import { cn, DIMENSION_LABELS, pct } from '../lib/format'

/** Semicircle gauge for "clean rows %", with an optional after value drawn on top. */
export function ScoreGauge({ before, after, label = 'Clean rows' }: { before: number; after?: number; label?: string }) {
  const r = 70, cx = 90, cy = 86, len = Math.PI * r
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`
  const shown = after ?? before
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 180 100" className="w-56" role="img" aria-label={`${label} ${pct(before)}${after !== undefined ? ` to ${pct(after)}` : ''}`}>
        <path d={arc} fill="none" strokeWidth="14" strokeLinecap="round" className="stroke-slate-200 dark:stroke-slate-800" />
        <path d={arc} fill="none" strokeWidth="14" strokeLinecap="round" className="stroke-rose-400"
          strokeDasharray={`${(before / 100) * len} ${len}`} />
        {after !== undefined && (
          <path d={arc} fill="none" strokeWidth="14" strokeLinecap="round" className="stroke-emerald-500 transition-all duration-700"
            strokeDasharray={`${(after / 100) * len} ${len}`} />
        )}
        <text x={cx} y={cy - 12} textAnchor="middle" className="fill-current text-[26px] font-semibold tabular">{pct(shown)}</text>
      </svg>
      <div className="-mt-1 text-sm text-slate-500 dark:text-slate-400">
        {label}{after !== undefined && <> · was <span className="tabular">{pct(before)}</span></>}
      </div>
    </div>
  )
}

export function DimensionBars({ before, after }: { before: Dimensions; after?: Dimensions }) {
  const dims = ['completeness', 'validity', 'consistency', 'uniqueness'] as const
  return (
    <div className="space-y-3">
      {dims.map((d) => (
        <div key={d}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="font-medium">{DIMENSION_LABELS[d]}</span>
            <span className="tabular text-slate-500">{pct(before[d])}{after && <> → <b className="text-emerald-600">{pct(after[d])}</b></>}</span>
          </div>
          <div className="relative h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
            {after && <div className="absolute inset-y-0 left-0 rounded-full bg-emerald-500 transition-all duration-700" style={{ width: `${after[d]}%` }} />}
            <div className="absolute inset-y-0 left-0 rounded-full bg-rose-400/90" style={{ width: `${before[d]}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Columns × row blocks, colour = share of rows in the block with a problem in that column. */
export function Heatmap({ data, onPick }: { data: HeatmapData; onPick?: (block: number, column: string) => void }) {
  const [hover, setHover] = useState<{ b: number; c: number } | null>(null)
  const max = Math.max(data.max, 0.0001)
  const shade = (v: number) => {
    if (v === 0) return 'transparent'
    const t = Math.min(1, Math.sqrt(v / max))
    return `rgba(225, 29, 72, ${0.12 + 0.88 * t})`
  }
  const h = hover
  return (
    <div>
      <div className="overflow-x-auto">
        <div className="inline-grid gap-px" style={{ gridTemplateColumns: `repeat(${data.columns.length}, minmax(22px, 1fr))` }}>
          {data.columns.map((c) => (
            <div key={c} className="h-24 truncate text-[10px] text-slate-500 [writing-mode:vertical-rl] rotate-180 text-left" title={c}>{c}</div>
          ))}
          {data.cells.map((row, b) => row.map((v, c) => (
            <button key={`${b}-${c}`} onMouseEnter={() => setHover({ b, c })} onMouseLeave={() => setHover(null)}
              onClick={() => v > 0 && onPick?.(b, data.columns[c])}
              className={cn('h-2.5 border-0 bg-slate-100 dark:bg-slate-800', v > 0 && 'cursor-pointer hover:outline hover:outline-1 hover:outline-slate-900')}
              style={{ backgroundColor: v > 0 ? shade(v) : undefined }}
              aria-label={`${data.columns[c]}, rows ${b * data.block_size + 1} to ${(b + 1) * data.block_size}: ${pct(v * 100)}`} />
          )))}
        </div>
      </div>
      <div className="mt-2 h-5 text-xs text-slate-500">
        {h ? <>rows {(h.b * data.block_size).toLocaleString()}–{((h.b + 1) * data.block_size - 1).toLocaleString()} ·{' '}
          <b>{data.columns[h.c]}</b> · {pct(data.cells[h.b][h.c] * 100)} of rows have a problem{data.cells[h.b][h.c] > 0 && ' · click to see them'}</>
          : `Each cell = ${data.block_size} rows. Darker = more problems. Stripes show where errors cluster.`}
      </div>
    </div>
  )
}
