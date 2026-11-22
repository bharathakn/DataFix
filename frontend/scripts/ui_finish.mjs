// Phase 6B check: chat panel, Privacy, Export in headless Chrome.
// node scripts/ui_finish.mjs <outDir> [baseUrl]  (backend on :8000, vite on :5173)
import { chromium } from 'playwright-core'

const out = process.argv[2] || 'shots'
const base = process.argv[3] || 'http://localhost:5173'
const api = async (method, path, body) => {
  const r = await fetch(`${base}/api${path}`, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`)
  return r.json()
}
const t0 = Date.now()
const log = (s) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${s}`)
const sid = (await api('POST', '/sessions/demo')).session_id
await api('POST', `/sessions/${sid}/scan`, { overrides: {} })
await api('POST', `/sessions/${sid}/repair/plan`, {})
await api('POST', `/sessions/${sid}/repair/apply-auto`)
log(`session ${sid} prepared`)

const errors = []
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(String(e)))
const shot = async (name) => { await page.screenshot({ path: `${out}/${name}.png` }); log(`shot ${name}`) }

// Chat
await page.goto(`${base}/s/${sid}`)
await page.getByRole('button', { name: 'Chat', exact: true }).click()
for (const q of ['How many customers are in Pune?', 'Why did row 412 change?', 'Why did row 643 not change?']) {
  const before = await page.locator('[data-testid="assistant-turn"]').count()
  const input = page.getByLabel('Chat message')
  await input.fill(q)
  await input.press('Enter')
  await page.waitForFunction((n) => document.querySelectorAll('[data-testid="assistant-turn"]').length > n, before, { timeout: 30000 })
  log(`asked: ${q} -> ${(await page.locator('[data-testid="assistant-turn"]').last().innerText()).split('\n')[0].slice(0, 110)}`)
}
await page.getByText(/Ran \d quer/).first().click()
await page.waitForTimeout(300)
await shot('30-chat')
await page.getByLabel('Chat message').fill('Undo the city fixes')
await page.getByLabel('Chat message').press('Enter')
await page.getByRole('button', { name: 'Confirm' }).waitFor({ timeout: 30000 })
const cityBefore = (await api('GET', `/sessions/${sid}/changes?column=city&action=apply&limit=1000`)).items.filter((c) => c.status === 'applied').length
await page.getByRole('button', { name: 'Confirm' }).click()
await page.getByText(/^Done: Undo all/).waitFor({ timeout: 15000 })
const cityAfter = (await api('GET', `/sessions/${sid}/changes?column=city&action=apply&limit=1000`)).items.filter((c) => c.status === 'applied').length
log(`chat undo confirmed: applied city changes ${cityBefore} -> ${cityAfter}`)
await shot('31-chat-undo')
await page.getByLabel('Close chat').click()

// Privacy
await page.goto(`${base}/s/${sid}/privacy`)
await page.getByRole('heading', { name: 'Personal data found' }).waitFor()
await page.waitForTimeout(500)
await shot('32-privacy')
await page.getByRole('button', { name: /Mask all high-risk/ }).click()
await page.getByText(/^Masked [\d,]+ high-risk values/).waitFor({ timeout: 30000 })
await page.waitForTimeout(800)
await shot('33-privacy-masked')
const row = await api('GET', `/sessions/${sid}/rows?column=notes&issue_type=&limit=500`)
const notes = (await api('GET', `/sessions/${sid}/privacy`)).filter((f) => f.column === 'notes')
log(`notes masked=${notes.every((f) => f.masked)} method=${notes[0].method}`)
const pan = (await api('GET', `/sessions/${sid}/privacy`)).find((f) => f.column === 'pan')
log(`pan masked=${pan.masked} method=${pan.method}; rows page ok=${row.total >= 0}`)

// Export
await page.goto(`${base}/s/${sid}/export`)
await page.getByText(/do-no-harm checks passed|check\(s\) failed/).waitFor({ timeout: 60000 })
log(`export status: ${await page.getByText(/do-no-harm checks passed|check\(s\) failed/).innerText()}`)
const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.getByRole('button', { name: /Download all/ }).click()])
log(`zip download: ${dl.suggestedFilename()}`)
await page.getByRole('button', { name: 'Show preview' }).click()
await page.frameLocator('iframe[title="Quality report"]').getByText('DataFix Quality Report').waitFor({ timeout: 60000 })
await page.waitForTimeout(500)
await shot('34-export')
const validation = await api('GET', `/sessions/${sid}/validation`)
log(`validation after chat undo + masking: ${validation.checks.filter((c) => c.passed).length}/8 ${validation.checks.filter((c) => !c.passed).map((c) => c.name)}`)
console.log('console errors:', errors.length ? errors : 'none')
await browser.close()
