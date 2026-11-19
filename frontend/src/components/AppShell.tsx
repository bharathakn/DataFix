import {
  Activity, Download, FlaskConical, History, LayoutDashboard, MessageSquare, Moon, Search, ShieldCheck, Sun, Wrench,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { useLlmStatus, useSession } from '../api/hooks'
import { cn, num } from '../lib/format'
import { ChatPanel } from './ChatPanel'

const NAV = [
  { to: '', label: 'Overview', icon: LayoutDashboard, end: true },
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
    <span title={title} className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
      online ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300')}>
      <span className={cn('size-1.5 rounded-full', online ? 'bg-emerald-500' : 'bg-slate-400')} />
      {live ? (online ? (data.provider === 'groq' ? 'AI: Groq (backup)' : 'AI: Gemini') : 'AI: offline fallback') : 'AI: offline templates'}
    </span>
  )
}

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid size-7 place-items-center rounded-lg bg-brand-600 text-white"><Activity className="size-4" /></span>
      DataFix
    </Link>
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
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
        <Brand />
        {s && (
          <div className="hidden min-w-0 items-center gap-2 text-sm text-slate-500 md:flex dark:text-slate-400">
            <span className="truncate font-medium text-slate-700 dark:text-slate-200">{s.filename}</span>
            <span>·</span>
            <span className="tabular">{num(s.rows_current)} rows</span>
            {s.linked_tables.map((t) => <span key={t.name}>+ {t.name} ({num(t.rows)})</span>)}
          </div>
        )}
        <div className="ml-auto flex items-center gap-3">
          {before !== undefined && (
            <span className="tabular hidden text-sm sm:inline" title="Quality score: before → now">
              Score <b>{before}</b>{now !== undefined && now !== before && <> → <b className="text-emerald-600">{now}</b></>}
            </span>
          )}
          <LlmPill />
          <button className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => setDark(!dark)}
            aria-label="Toggle dark mode">{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}</button>
          <button onClick={() => setChat(!chat)} aria-pressed={chat}
            className={cn('inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm', chat
              ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800')}>
            <MessageSquare className="size-4" />Chat</button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav className="hidden w-52 shrink-0 flex-col gap-0.5 border-r border-slate-200 bg-white p-3 md:flex dark:border-slate-800 dark:bg-slate-900">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={label} to={`/s/${sid}${to ? `/${to}` : ''}`} end={end}
              className={({ isActive }) => cn('flex items-center gap-2.5 rounded-md px-3 py-2 text-sm',
                isActive ? 'bg-brand-50 font-medium text-brand-700 dark:bg-brand-700/20 dark:text-brand-100'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800')}>
              <Icon className="size-4" />{label}
            </NavLink>
          ))}
        </nav>
        <main className={cn('min-w-0 flex-1 overflow-auto', chat && 'lg:mr-[28rem]')}>{children}</main>
      </div>
      {chat && sid && <ChatPanel sid={sid} session={s} onClose={() => setChat(false)} />}
    </div>
  )
}
