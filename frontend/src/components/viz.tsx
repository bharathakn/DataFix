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
        <path d={arc} fill="none" strokeWidth="14" strokeLinecap="round"
          className={after !== undefined ? 'stroke-slate-300 dark:stroke-slate-600' : 'stroke-brand-600 dark:stroke-brand-400'}
          strokeDasharray={`${(before / 100) * len} ${len}`} />
        {after !== undefined && (
          <path d={arc} fill="none" strokeWidth="14" strokeLinecap="round" className="stroke-brand-600 transition-all duration-700 dark:stroke-brand-400"
            strokeDasharray={`${(after / 100) * len} ${len}`} />
        )}
        <text x={cx} y={cy - 12} textAnchor="middle" className="fill-current font-display text-[30px] tabular">{pct(shown)}</text>
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
    <div className="space-y-4">
      {dims.map((d) => (
        <div key={d}>
          <div className="mb-1.5 flex justify-between text-[13px]">
            <span className="font-medium">{DIMENSION_LABELS[d]}</span>
            <span className="tabular text-slate-500">{pct(before[d])}{after && <> → <b className="text-brand-600 dark:text-brand-300">{pct(after[d])}</b></>}</span>
          </div>
          <div className="relative h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            {after && <div className="absolute inset-y-0 left-0 rounded-full bg-brand-600 transition-all duration-700 dark:bg-brand-400" style={{ width: `${after[d]}%` }} />}
            <div className={cn('absolute inset-y-0 left-0 rounded-full', after ? 'bg-slate-300 dark:bg-slate-600' : 'bg-brand-600 dark:bg-brand-400')} style={{ width: `${before[d]}%` }} />
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
    return `rgba(180, 68, 47, ${0.12 + 0.88 * t})`
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

export interface Slice { label: string; value: number; color: string; onClick?: () => void }

/** Donut with a clickable legend; total in the middle. Colours are theme hex values (light and dark safe). */
export function Donut({ slices, unit = 'problems' }: { slices: Slice[]; unit?: string }) {
  const shown = slices.filter((s) => s.value > 0)
  const total = shown.reduce((a, s) => a + s.value, 0)
  const R = 84, C = 2 * Math.PI * R, gap = shown.length > 1 ? 2 : 0
  let acc = 0
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
      <svg viewBox="0 0 220 220" className="size-[190px] shrink-0" role="img"
        aria-label={`${total} ${unit}: ${shown.map((s) => `${s.label} ${s.value}`).join(', ')}`}>
        <g transform="rotate(-90 110 110)" fill="none" strokeWidth="26">
          {total === 0 && <circle cx="110" cy="110" r={R} className="stroke-slate-200 dark:stroke-slate-800" />}
          {shown.map((s) => {
            const len = Math.max(C * (s.value / total) - gap, 0.5)
            const el = <circle key={s.label} cx="110" cy="110" r={R} stroke={s.color} strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-acc} />
            acc += C * (s.value / total)
            return el
          })}
        </g>
        <text x="110" y="112" textAnchor="middle" className="fill-slate-900 font-display text-[30px] tabular dark:fill-slate-50">{total.toLocaleString('en-IN')}</text>
        <text x="110" y="134" textAnchor="middle" className="fill-slate-500 text-[12px]">{unit}</text>
      </svg>
      <ul className="flex min-w-[210px] flex-col gap-1">
        {slices.map((s) => (
          <li key={s.label}>
            <button type="button" onClick={s.onClick} disabled={!s.onClick || !s.value}
              className="flex w-full items-center justify-between gap-5 rounded-md px-2 py-1 text-left text-[13.5px] enabled:hover:bg-slate-100 disabled:cursor-default dark:enabled:hover:bg-slate-800">
              <span className="flex items-center gap-2"><span className="size-2.5 rounded-[3px]" style={{ background: s.color }} />{s.label}</span>
              <b className="tabular">{s.value.toLocaleString('en-IN')}</b>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
