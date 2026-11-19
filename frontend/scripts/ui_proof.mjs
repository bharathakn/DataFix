// Phase 6A check: Validation + Diagnosis in headless Chrome.
// node scripts/ui_proof.mjs <outDir> [baseUrl]  (backend on :8000, vite on :5173)
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
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(String(e)))
const shot = async (name, full = false) => { await page.screenshot({ path: `${out}/${name}.png`, fullPage: full }); log(`shot ${name}`) }

await page.goto(`${base}/s/${sid}/validation`)
await page.getByText(/\d \/ 8 passed/).waitFor({ timeout: 60000 })
log(`checks: ${await page.getByText(/\d \/ 8 passed/).innerText()}`)
await shot('20-validation', true)
await page.getByRole('button', { name: 'Run benchmark' }).click()
await page.getByText('False repair rate', { exact: true }).waitFor({ timeout: 90000 })
await page.waitForTimeout(500)
log('benchmark done')
await page.getByText('False repair rate', { exact: true }).scrollIntoViewIfNeeded()
await shot('21-benchmark')
await page.reload()
await page.getByText('False repair rate', { exact: true }).waitFor({ timeout: 30000 })
log('benchmark result survives reload')

await page.goto(`${base}/s/${sid}/diagnosis`)
await page.getByText('71 of 73 blank city').first().waitFor({ timeout: 30000 })
await page.waitForTimeout(500)
await shot('22-diagnosis', true)
await page.getByRole('button', { name: 'Show rows' }).nth(1).click()
await page.locator('table').waitFor()
await page.waitForTimeout(600)
await shot('23-diagnosis-rows')
await page.keyboard.press('Escape')
await page.getByRole('button', { name: 'Summarise with AI' }).click()
await page.locator('main').getByText(/AI unavailable: template|written by (Gemini|Groq)/).waitFor({ timeout: 30000 })
log('summary button works')

console.log('console errors:', errors.length ? errors : 'none')
await browser.close()
