import { useEffect, useState } from 'react'

export default function App() {
  const [health, setHealth] = useState('checking…')
  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setHealth(`${d.status} · engine ${d.version} · LLM ${d.llm}`))
      .catch(() => setHealth('backend not reachable'))
  }, [])
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 grid place-items-center">
      <div className="text-center space-y-2">
        <h1 className="text-4xl font-semibold">DataFix</h1>
        <p className="text-slate-500">find it, explain it, fix it safely, prove it</p>
        <p className="text-sm font-mono">{health}</p>
      </div>
    </main>
  )
}
