import {
  Columns3, Download, FilePlus2, FileText, FlaskConical, History, LayoutDashboard, MessageSquare, Moon, Search, ShieldCheck,
  Sun, Wrench,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { useLlmStatus, useSession } from '../api/hooks'
import { cn, num } from '../lib/format'
import { ChatPanel } from './ChatPanel'

const NAV = [
  { to: '', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: 'setup', label: 'Column types', icon: Columns3 },
  { to: 'diagnosis', label: 'Diagnosis', icon: Search },
  { to: 'repair', label: 'Repair Studio', icon: Wrench },
  { to: 'privacy', label: 'Privacy', icon: ShieldCheck },
  { to: 'validation', label: 'Validation', icon: FlaskConical },
  { to: 'history', label: 'History', icon: History },
  { to: 'export', label: 'Export', icon: Download },
]

function useTheme() {
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('datafix-theme') === 'dark' } catch { return false }
  })
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem('datafix-theme', dark ? 'dark' : 'light') } catch { /* private mode */ }
  }, [dark])
  return [dark, setDark] as const
}

export function LlmPill() {
  const { data } = useLlmStatus()
  const live = data?.provider === 'gemini' || data?.provider === 'groq'
  const online = live && data.ok !== false
  const backup = data?.backup?.configured ? ` · backup: Groq ${data.backup.model}` : ''
  const title = live
    ? `${data.provider === 'groq' ? 'Groq (backup)' : 'Gemini'} · ${data.model ?? ''}${backup}${data.last_error ? ` · last error: ${data.last_error}` : ''}`
    : 'No AI key: explanations and chat use built-in templates'
  return (
    <span title={title} className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold',
      online ? 'bg-brand-50 text-brand-600 dark:bg-brand-700/30 dark:text-brand-100' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300')}>
      <span className={cn('size-1.5 rounded-full', online ? 'bg-emerald-500' : 'bg-slate-400')} />
      {live ? (online ? (data.provider === 'groq' ? 'AI: Groq (backup)' : 'AI: Gemini') : 'AI: offline fallback') : 'AI: offline templates'}
    </span>
  )
}

export function Logo({ size = 'md' }: { size?: 'md' | 'lg' }) {
  return (
    <span className={cn('grid shrink-0 place-items-center bg-brand-600 font-display text-white',
      size === 'lg' ? 'size-[38px] rounded-[10px] text-[21px]' : 'size-8 rounded-lg text-lg')}>D</span>
  )
}

export function Brand({ sub }: { sub?: string }) {
  return (
    <Link to="/" className="flex items-center gap-3" title="Start with a new file">
      <Logo size="lg" />
      <span className="leading-tight">
        <span className="block font-display text-[21px] text-slate-900 dark:text-slate-50">DataFix</span>
        {sub && <span className="block text-xs text-slate-500 dark:text-slate-400">{sub}</span>}
      </span>
    </Link>
  )
}

function NavItems({ sid, compact }: { sid: string; compact?: boolean }) {
  return (
    <>
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={label} to={`/s/${sid}${to ? `/${to}` : ''}`} end={end}
          className={({ isActive }) => cn('flex shrink-0 items-center gap-3 rounded-[9px] text-[14px] transition-colors',
            compact ? 'px-3 py-1.5' : 'px-3 py-2.5',
            isActive ? 'bg-brand-50 font-semibold text-brand-600 dark:bg-brand-700/30 dark:text-brand-100'
              : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800')}>
          {({ isActive }) => <><Icon className={cn('size-[17px]', isActive ? 'opacity-100' : 'opacity-60')} />{label}</>}
        </NavLink>
      ))}
    </>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const { sid = '' } = useParams()
  const { data: s } = useSession(sid)
  const [dark, setDark] = useTheme()
  const [chat, setChat] = useState(false)
  const before = s?.quality_score
  const now = s?.score_now
  return (
    <div className="flex h-full">
      <aside className="hidden w-[232px] shrink-0 flex-col border-r border-slate-200 bg-white md:flex dark:border-slate-800 dark:bg-slate-900">
        <div className="border-b border-slate-200 px-5 py-[22px] dark:border-slate-800"><Brand sub="Data quality studio" /></div>
        <nav className="flex flex-col gap-0.5 p-3" aria-label="Sections"><NavItems sid={sid} /></nav>
        <div className="mt-auto space-y-3 border-t border-slate-200 p-4 dark:border-slate-800">
          <div className="flex items-center justify-between gap-2">
            <LlmPill />
            <button className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => setDark(!dark)}
              aria-label="Toggle dark mode" title={dark ? 'Light mode' : 'Dark mode'}>{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}</button>
          </div>
          <Link to="/" className="flex items-center gap-2 rounded-lg px-1 text-sm text-slate-600 hover:text-brand-600 dark:text-slate-300">
            <FilePlus2 className="size-4" />New file</Link>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 px-6 pb-1 pt-5 lg:px-9">
          <div className="md:hidden"><Brand /></div>
          {s && (
            <div className="hidden min-w-0 items-center gap-1.5 text-[13px] text-slate-500 md:flex dark:text-slate-400">
              <FileText className="size-4 opacity-70" />
              <span className="truncate font-semibold text-slate-900 dark:text-slate-100">{s.filename}</span>
              <span>·</span>
              <span className="tabular">{num(s.rows_current)} rows</span>
              {s.linked_tables.map((t) => <span key={t.name} className="tabular">+ {t.name} ({num(t.rows)})</span>)}
            </div>
          )}
          <div className="ml-auto flex items-center gap-3">
            {before !== undefined && (
              <span className="tabular hidden whitespace-nowrap rounded-full bg-white px-3 py-1 text-[13px] text-slate-600 ring-1 ring-slate-200 sm:inline dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800"
                title="Quality score: before → now">
                Quality score <b className="text-slate-900 dark:text-slate-100">{before}</b>
                {now !== undefined && now !== before && <> → <b className="text-emerald-600 dark:text-emerald-300">{now}</b></>}
              </span>
            )}
            <span className="md:hidden"><LlmPill /></span>
            <button className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden dark:hover:bg-slate-800" onClick={() => setDark(!dark)}
              aria-label="Toggle dark mode">{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}</button>
            <button onClick={() => setChat(!chat)} aria-pressed={chat}
              className={cn('inline-flex items-center gap-1.5 rounded-[10px] border px-3.5 py-2 text-sm font-semibold transition-colors', chat
                ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white text-slate-900 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800')}>
              <MessageSquare className="size-4" />Chat</button>
          </div>
          <nav className="-mx-1 flex w-full gap-1 overflow-x-auto pb-1 md:hidden" aria-label="Sections (mobile)"><NavItems sid={sid} compact /></nav>
        </header>
        <main className={cn('min-w-0 flex-1 overflow-auto', chat && 'lg:mr-[28rem]')}>{children}</main>
      </div>
      {chat && sid && <ChatPanel sid={sid} session={s} onClose={() => setChat(false)} />}
    </div>
  )
}
