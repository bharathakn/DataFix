import { Loader2, X } from 'lucide-react'
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '../lib/format'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({ variant = 'secondary', loading, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: 'border border-brand-600 bg-brand-600 text-white hover:border-brand-700 hover:bg-brand-700 dark:border-brand-500 dark:bg-brand-500 dark:hover:bg-brand-400',
    secondary: 'border border-slate-300 bg-white text-slate-900 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800',
    ghost: 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
    danger: 'border border-rose-500 bg-rose-500 text-white hover:bg-rose-600',
  }
  return (
    <button
      className={cn('inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] px-4 py-2.5 text-sm font-semibold transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500',
        styles[variant], className)}
      disabled={disabled || loading} {...rest}>
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  )
}

export function Card({ title, subtitle, action, children, className }:
  { title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('min-w-0 rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-5">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
            {subtitle && <div className="mt-1 text-[12.5px] leading-snug text-slate-500 dark:text-slate-400">{subtitle}</div>}
          </div>
          {action}
        </header>
      )}
      <div className={cn('p-5', (title || action) ? 'pt-4' : '')}>{children}</div>
    </section>
  )
}

/** Page title block used by every screen: serif title, one-line explanation, actions on the right. */
export function PageHeader({ title, lead, actions }: { title: ReactNode; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-[60rem]">
        <h1 className="font-display text-[34px] leading-[1.12] text-slate-900 dark:text-slate-50">{title}</h1>
        {lead && <p className="mt-2.5 max-w-3xl text-[14.5px] leading-relaxed text-slate-500 dark:text-slate-400">{lead}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

type Tone = 'slate' | 'green' | 'amber' | 'red' | 'blue' | 'violet'
const TONES: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  green: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-200',
  amber: 'bg-amber-50 text-amber-700 dark:bg-amber-900/50 dark:text-amber-200',
  red: 'bg-rose-50 text-rose-500 dark:bg-rose-900/50 dark:text-rose-200',
  blue: 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200',
  violet: 'bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200',
}

export function Badge({ tone = 'slate', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold', TONES[tone], className)}>{children}</span>
}

export function Kpi({ label, value, hint, tone, onClick }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone; onClick?: () => void }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag onClick={onClick}
      className={cn('flex min-w-0 flex-col items-start justify-start rounded-2xl border border-slate-200 bg-white p-5 text-left dark:border-slate-800 dark:bg-slate-900',
        onClick && 'transition hover:border-brand-400 hover:bg-slate-50/60 dark:hover:bg-slate-800/60')}>
      <div className="text-[13px] text-slate-500 dark:text-slate-400">{label}</div>
      <div className={cn('tabular mt-2.5 font-display text-[34px] leading-none', tone === 'red' && 'text-rose-500', tone === 'green' && 'text-brand-600 dark:text-brand-300',
        tone === 'amber' && 'text-amber-500')}>{value}</div>
      {hint && <div className="mt-2.5 text-[12.5px] leading-snug text-slate-500 dark:text-slate-400">{hint}</div>}
    </Tag>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="size-4 animate-spin" />{label}</div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-slate-200 dark:bg-slate-800', className)} />
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  const msg = error instanceof Error ? error.message : String(error)
  return <div className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">{msg}</div>
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      {icon && <div className="text-slate-400">{icon}</div>}
      <div className="font-medium">{title}</div>
      {children && <div className="max-w-md text-sm text-slate-500 dark:text-slate-400">{children}</div>}
    </div>
  )
}

export function Drawer({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/35 backdrop-blur-[1px]" onClick={onClose} />
      <aside className={cn('relative flex h-full w-full flex-col bg-white shadow-2xl dark:bg-slate-900', wide ? 'max-w-6xl' : 'max-w-xl')}>
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <h2 className="font-display text-xl">{title}</h2>
          <Button variant="ghost" onClick={onClose} aria-label="Close"><X className="size-4" /></Button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-5">{children}</div>
      </aside>
    </div>
  )
}

export const STATE_LEGEND: { state: string; label: string }[] = [
  { state: 'issue', label: 'Problem found' }, { state: 'repaired', label: 'Repaired' },
  { state: 'review', label: 'Needs review' }, { state: 'flagged', label: 'Flagged / refused' },
  { state: 'estimated', label: 'Estimated' }, { state: 'masked', label: 'Masked' },
]

export function Legend() {
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {STATE_LEGEND.map((s) => (
        <span key={s.state} className={cn('rounded px-2 py-0.5', `cell-${s.state}`)}>{s.label}</span>
      ))}
    </div>
  )
}
