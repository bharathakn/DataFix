import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot, ChevronRight, Send, Terminal, Undo2, User, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ChatReply, SessionSummary } from '../api/types'
import { cn } from '../lib/format'
import { useToast } from './toast'
import { Badge, Button } from './ui'

interface Turn { role: 'user' | 'assistant'; text: string; reply?: ChatReply; error?: boolean }

const SUGGESTIONS = [
  'How many customers are in Pune?', 'Why did row 52 change?', 'Why did row 643 not change?',
  'Which repairs are you least sure about?', 'Show duplicates in the email column', 'Undo the city fixes',
]

function ToolCalls({ calls }: { calls: ChatReply['tool_calls'] }) {
  if (!calls.length) return null
  return (
    <details className="mt-2 rounded-lg bg-slate-100 px-2 py-1.5 text-xs dark:bg-slate-800">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-slate-600 dark:text-slate-300">
        <Terminal className="size-3.5" />Ran {calls.length} {calls.length === 1 ? 'query' : 'queries'} on your data <ChevronRight className="size-3" />
      </summary>
      <div className="mt-1.5 space-y-1.5">
        {calls.map((c, i) => (
          <div key={i}>
            <code className="font-mono text-[11px] text-brand-700 dark:text-brand-100">{c.name}({JSON.stringify(c.args)})</code>
            <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap break-all text-[10px] text-slate-500">{JSON.stringify(c.result_preview).slice(0, 600)}</pre>
          </div>
        ))}
      </div>
    </details>
  )
}

function AssistantTurn({ t, sid }: { t: Turn; sid: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [done, setDone] = useState(false)
  const confirm = useMutation({
    mutationFn: async () => {
      const a = t.reply!.proposed_action!
      if (a.kind === 'undo_checkpoint') await api.undoCheckpoint(sid, a.payload.checkpoint_id!)
      else await api.undoChanges(sid, a.payload.change_ids!)
    },
    onSuccess: () => { setDone(true); qc.invalidateQueries({ queryKey: [sid] }); toast({ text: 'Done: ' + t.reply!.proposed_action!.label }) },
  })
  const r = t.reply
  return (
    <div className="flex gap-2" data-testid="assistant-turn">
      <div className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand-600 text-white"><Bot className="size-3.5" /></div>
      <div className={cn('min-w-0 flex-1 rounded-lg px-3 py-2 text-sm', t.error ? 'bg-rose-50 text-rose-800 dark:bg-rose-950 dark:text-rose-200' : 'bg-white dark:bg-slate-800')}>
        <div className="whitespace-pre-wrap">{t.text}</div>
        {r?.table && r.table.rows.length > 0 && (
          <div className="mt-2 max-h-48 overflow-auto rounded border border-slate-200 dark:border-slate-700">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 dark:bg-slate-900"><tr>{r.table.columns.map((c) => <th key={c} className="px-2 py-1 text-left font-medium">{c}</th>)}</tr></thead>
              <tbody>{r.table.rows.map((row, i) => <tr key={i} className="border-t border-slate-100 dark:border-slate-700">{row.map((v, j) => <td key={j} className="px-2 py-1">{v}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )}
        {r?.proposed_action && (
          <div className="mt-2 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs dark:border-amber-800 dark:bg-amber-950">
            <span className="flex-1">{r.proposed_action.label}?</span>
            {done ? <Badge tone="green">done</Badge> : (
              <Button variant="primary" className="px-2 py-1 text-xs" loading={confirm.isPending} onClick={() => confirm.mutate()}>
                <Undo2 className="size-3.5" />Confirm</Button>
            )}
          </div>
        )}
        {r && <ToolCalls calls={r.tool_calls} />}
        {r && <div className="mt-1 text-[10px] text-slate-400">{r.mode === 'offline' ? 'offline mode: built-in question patterns' : `${r.mode === 'groq' ? 'Groq (backup)' : 'Gemini'} chose the queries; the numbers come from DataFix`}</div>}
      </div>
    </div>
  )
}

export function ChatPanel({ sid, session, onClose }: { sid: string; session?: SessionSummary; onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const ready = session && (session.stage === 'planned' || session.stage === 'repairing')
  const ask = useMutation({
    mutationFn: (q: string) => api.chat(sid, q, turns.filter((t) => !t.error).slice(-6).map((t) => ({ role: t.role, text: t.text }))),
    onSuccess: (r) => setTurns((ts) => [...ts, { role: 'assistant', text: r.text, reply: r }]),
    onError: (e) => setTurns((ts) => [...ts, { role: 'assistant', text: e instanceof Error ? e.message : String(e), error: true }]),
  })
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, ask.isPending])
  const send = (q: string) => {
    const msg = q.trim()
    if (!msg || ask.isPending) return
    setTurns((ts) => [...ts, { role: 'user', text: msg }])
    setText('')
    ask.mutate(msg)
  }
  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-slate-200 bg-slate-50 shadow-2xl dark:border-slate-800 dark:bg-slate-950">
      <header className="flex items-start justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900">
        <div>
          <div className="font-display text-xl">Ask about your data</div>
          <div className="mt-0.5 text-xs text-slate-500">Answers come from queries DataFix runs. Personal data stays masked.</div>
        </div>
        <Button variant="ghost" onClick={onClose} aria-label="Close chat"><X className="size-4" /></Button>
      </header>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
        {!ready && <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">Scan and plan repairs first; then ask anything about the data and the repairs.</div>}
        {turns.length === 0 && ready && (
          <div className="space-y-2">
            <div className="text-sm text-slate-600 dark:text-slate-400">Try one of these:</div>
            {SUGGESTIONS.map((q) => (
              <button key={q} onClick={() => send(q)} className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm hover:border-brand-500 dark:border-slate-700 dark:bg-slate-900">{q}</button>
            ))}
          </div>
        )}
        {turns.map((t, i) => t.role === 'user' ? (
          <div key={i} className="flex justify-end gap-2">
            <div className="max-w-[85%] rounded-lg bg-brand-600 px-3 py-2 text-sm text-white">{t.text}</div>
            <div className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-slate-300 dark:bg-slate-700"><User className="size-3.5" /></div>
          </div>
        ) : <AssistantTurn key={i} t={t} sid={sid} />)}
        {ask.isPending && <div className="flex items-center gap-2 pl-8 text-sm text-slate-500"><span className="size-2 animate-pulse rounded-full bg-brand-500" />Running queries…</div>}
        <div ref={end} />
      </div>
      <form className="flex gap-2 border-t border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900" onSubmit={(e) => { e.preventDefault(); send(text) }}>
        <input value={text} onChange={(e) => setText(e.target.value)} disabled={!ready} placeholder="e.g. How many customers are in Pune?" aria-label="Chat message"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800" />
        <Button type="submit" variant="primary" disabled={!ready || !text.trim()} loading={ask.isPending} aria-label="Send"><Send className="size-4" /></Button>
      </form>
    </aside>
  )
}
