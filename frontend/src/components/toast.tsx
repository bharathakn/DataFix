import { CheckCircle2, X } from 'lucide-react'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

interface Toast { id: number; text: ReactNode; action?: { label: string; run: () => void } }

const Ctx = createContext<(t: Omit<Toast, 'id'>) => void>(() => {})

export function useToast() {
  return useContext(Ctx)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setItems((xs) => [...xs, { ...t, id }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 8000)
  }, [])
  const close = (id: number) => setItems((xs) => xs.filter((x) => x.id !== id))
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto flex items-center gap-3 rounded-lg bg-slate-900 px-4 py-2.5 text-sm text-white shadow-xl dark:bg-slate-100 dark:text-slate-900">
            <CheckCircle2 className="size-4 text-emerald-400 dark:text-emerald-600" />
            <span>{t.text}</span>
            {t.action && (
              <button className="font-semibold text-brand-100 underline-offset-2 hover:underline dark:text-brand-600"
                onClick={() => { t.action!.run(); close(t.id) }}>{t.action.label}</button>
            )}
            <button onClick={() => close(t.id)} aria-label="Dismiss" className="opacity-60 hover:opacity-100"><X className="size-3.5" /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
