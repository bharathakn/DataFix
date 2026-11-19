import { useMutation } from '@tanstack/react-query'
import { Database, FileSpreadsheet, Link2, Sparkles, Upload as UploadIcon } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Brand, LlmPill } from '../components/AppShell'
import { Badge, Button, ErrorNote } from '../components/ui'
import { cn } from '../lib/format'

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xls,.json'

function DropZone({ label, hint, file, onFile, icon, small, tag }:
  { label: string; hint: string; file: File | null; onFile: (f: File | null) => void; icon: React.ReactNode; small?: boolean; tag?: string }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0])
  }
  return (
    <div onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={onDrop}
      onClick={() => input.current?.click()} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
      className={cn('flex cursor-pointer items-center justify-center rounded-[18px] border-[1.5px] border-dashed text-center transition',
        small ? 'flex-wrap gap-x-3.5 gap-y-1.5 px-6 py-5' : 'flex-col gap-1 px-6 py-10',
        over ? 'border-brand-500 bg-brand-50 dark:bg-brand-700/10' : 'border-slate-300 bg-white hover:border-brand-400 dark:border-slate-700 dark:bg-slate-900')}>
      {small ? (
        <>
          <span className="text-slate-400">{icon}</span>
          {file
            ? <span className="font-medium">{file.name} <span className="text-xs font-normal text-slate-500">· {(file.size / 1024).toFixed(0)} KB · click to change</span></span>
            : <span className="text-slate-600 dark:text-slate-300">{label}</span>}
          {tag && !file && <Badge>{tag}</Badge>}
        </>
      ) : (
        <>
          <span className={cn('mb-2 grid size-[52px] place-items-center rounded-[14px]', file
            ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/40' : 'bg-brand-50 text-brand-600 dark:bg-brand-700/30 dark:text-brand-100')}>{icon}</span>
          {file ? (
            <>
              <div className="text-base font-semibold">{file.name}</div>
              <div className="text-xs text-slate-500">{(file.size / 1024).toFixed(0)} KB · click to change</div>
            </>
          ) : (
            <>
              <div className="text-base font-semibold">{label}</div>
              <div className="text-xs text-slate-500">{hint}</div>
              <span className="mt-3 inline-flex rounded-[9px] border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-semibold dark:border-slate-700 dark:bg-slate-900">Choose file</span>
            </>
          )}
        </>
      )}
      <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </div>
  )
}

export default function Upload() {
  const nav = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [linked, setLinked] = useState<File | null>(null)
  const go = (sid: string) => nav(`/s/${sid}/setup`)
  const demo = useMutation({ mutationFn: api.createDemo, onSuccess: (s) => go(s.session_id) })
  const upload = useMutation({ mutationFn: () => api.upload(file!, linked), onSuccess: (s) => go(s.session_id) })
  return (
    <div className="min-h-full">
      <div className="mx-auto max-w-[880px] px-6 pb-16 pt-11">
        <header className="mb-9 flex items-center justify-between gap-3"><Brand /><LlmPill /></header>
        <h1 className="font-display text-[40px] leading-[1.1] text-slate-900 dark:text-slate-50">Find it, explain it, fix it safely, prove it.</h1>
        <p className="mt-3 max-w-[700px] text-[15px] leading-relaxed text-slate-500 dark:text-slate-400">
          Upload a CSV, Excel or JSON file. DataFix finds what is wrong, explains why it happened, repairs only what the
          evidence supports, and proves nothing valid was changed. Your original file is never modified.
        </p>

        <div className="mt-7 grid gap-3.5">
          <DropZone label="Drop your data file here" hint="CSV, Excel or JSON · up to 200 MB" file={file} onFile={setFile}
            icon={<FileSpreadsheet className="size-6" />} />
          <DropZone small label="Optional: a linked table (for example, orders)" hint="" tag="Used as evidence to recover phones and emails"
            file={linked} onFile={setLinked} icon={<Link2 className="size-4" />} />
        </div>
        <div className="mt-[18px] flex flex-wrap items-center gap-3">
          <Button variant="primary" disabled={!file} loading={upload.isPending} onClick={() => upload.mutate()}>
            <UploadIcon className="size-4" />Upload and inspect
          </Button>
          <span className="text-sm text-slate-500">or</span>
          <Button loading={demo.isPending} onClick={() => demo.mutate()}>
            <Sparkles className="size-4" />Load demo dataset
          </Button>
        </div>
        <div className="mt-3"><ErrorNote error={upload.error || demo.error} /></div>

        <div className="mt-6 flex items-start gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-[18px] dark:border-slate-800 dark:bg-slate-900">
          <span className="grid size-10 shrink-0 place-items-center rounded-[11px] bg-amber-50 text-amber-500 dark:bg-amber-900/40"><Database className="size-[18px]" /></span>
          <div>
            <div className="font-semibold">Demo dataset</div>
            <p className="mt-1.5 leading-relaxed text-slate-500 dark:text-slate-400">
              10,200 Indian customer records plus 23,060 linked orders, with 1,678 realistic errors planted: blanks from one
              mobile-app batch, Excel-damaged phone numbers, misspelt cities, 5-digit PIN codes, duplicates, and Aadhaar and
              PAN numbers hidden in free-text notes.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-4">
          {[['Find', 'Every problem, cell by cell'], ['Explain', 'Which source or batch caused it'], ['Fix safely', 'Only with evidence; undo anytime'], ['Prove it', '8 do-no-harm checks']].map(([t, d], i) => (
            <div key={t} className="rounded-xl px-1">
              <div className="flex items-center gap-2 text-[13px] font-semibold"><span className="tabular font-display text-lg text-brand-600 dark:text-brand-300">{i + 1}</span>{t}</div>
              <div className="mt-0.5 text-[12.5px] text-slate-500">{d}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
