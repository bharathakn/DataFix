import { useMutation } from '@tanstack/react-query'
import { Database, FileSpreadsheet, Link2, Sparkles, Upload as UploadIcon } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Brand, LlmPill } from '../components/AppShell'
import { Button, ErrorNote } from '../components/ui'
import { cn } from '../lib/format'

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xls,.json'

function DropZone({ label, hint, file, onFile, icon, small }:
  { label: string; hint: string; file: File | null; onFile: (f: File | null) => void; icon: React.ReactNode; small?: boolean }) {
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
      className={cn('flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed text-center transition',
        small ? 'p-5' : 'p-10',
        over ? 'border-brand-500 bg-brand-50 dark:bg-brand-700/10' : 'border-slate-300 bg-white hover:border-brand-500 dark:border-slate-700 dark:bg-slate-900')}>
      <div className="text-slate-400">{icon}</div>
      {file ? (
        <div><div className="font-medium">{file.name}</div><div className="text-xs text-slate-500">{(file.size / 1024).toFixed(0)} KB · click to change</div></div>
      ) : (
        <div><div className="font-medium">{label}</div><div className="text-xs text-slate-500">{hint}</div></div>
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
      <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
        <Brand /><LlmPill />
      </header>
      <div className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-3xl font-semibold tracking-tight">Find it, explain it, fix it safely, prove it.</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Upload a CSV, Excel or JSON file. DataFix finds what's wrong, explains why it happened, repairs only what the
          evidence supports, and proves nothing valid was changed. Your original file is never modified.
        </p>

        <div className="mt-8 grid gap-4">
          <DropZone label="Drop your data file here" hint="CSV, Excel or JSON · up to 200 MB" file={file} onFile={setFile}
            icon={<FileSpreadsheet className="size-8" />} />
          <DropZone small label="Optional: a linked table (e.g. orders)" hint="Used as evidence to recover phones and emails"
            file={linked} onFile={setLinked} icon={<Link2 className="size-5" />} />
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" disabled={!file} loading={upload.isPending} onClick={() => upload.mutate()}>
              <UploadIcon className="size-4" />Upload and inspect
            </Button>
            <span className="text-sm text-slate-500">or</span>
            <Button loading={demo.isPending} onClick={() => demo.mutate()}>
              <Sparkles className="size-4" />Load demo dataset
            </Button>
          </div>
          <ErrorNote error={upload.error || demo.error} />
        </div>

        <div className="mt-10 rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          <div className="mb-2 flex items-center gap-2 font-medium text-slate-800 dark:text-slate-200"><Database className="size-4" />Demo dataset</div>
          10,200 Indian customer records plus 23,060 linked orders, with 1,678 realistic errors planted: blanks from one
          mobile-app batch, Excel-damaged phone numbers, misspelt cities, 5-digit PIN codes, duplicates, and Aadhaar /
          PAN numbers hidden in free-text notes.
        </div>
      </div>
    </div>
  )
}
