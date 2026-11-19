// Phase 5B check: Repair Studio + History in headless Chrome.
// node scripts/ui_repair.mjs <outDir> [baseUrl]  (backend on :8000, vite on :5173)
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
const evidenceTitle = () => page.locator('[data-testid="evidence-record"]').innerText()

// Review queue
await page.goto(`${base}/s/${sid}/repair`)
await page.locator('[data-testid="evidence"]').waitFor()
await page.waitForTimeout(600)
await shot('10-review')
const first = await evidenceTitle()
await page.keyboard.press('a')
await page.waitForFunction((t) => document.querySelector('[data-testid="evidence-record"]')?.innerText !== t, first, { timeout: 15000 })
log(`accepted with A: "${first.replace(/\n/g, ' ')}" -> next "${(await evidenceTitle()).replace(/\n/g, ' ')}"`)
await page.keyboard.press('j')
await page.waitForTimeout(400)

// Refused: row 1043 phone
await page.getByRole('button', { name: /^Refused/ }).click()
await page.getByLabel('Filter by column').selectOption('phone')
await page.waitForTimeout(800)
await page.locator('[data-pid]', { hasText: 'C-11044' }).first().click()
await page.getByText('DataFix refused to guess').waitFor()
await page.waitForTimeout(500)
await shot('11-refused-1043')

// Applied: row 412 pin
await page.getByRole('button', { name: /^Applied/ }).click()
await page.getByLabel('Filter by column').selectOption('pin')
await page.waitForTimeout(800)
await page.locator('[data-pid]', { hasText: 'C-10413' }).first().click()
await page.getByText('Undo this repair').waitFor()
await page.waitForTimeout(500)
await shot('12-applied-412')

// Merge card
await page.getByRole('button', { name: /^Review/ }).click()
await page.getByLabel('Filter by column').selectOption('__row__')
await page.waitForTimeout(900)
if (await page.locator('[data-pid]').count()) {
  await page.locator('[data-pid]').first().click()
  await page.getByText(/Survivor · row/).waitFor()
  await shot('14-merge')
}

// Patterns: bulk accept the first group
await page.getByRole('button', { name: /^Patterns/ }).click()
await page.getByRole('button', { name: 'Accept all', exact: true }).first().waitFor()
await shot('13-patterns')
await page.getByRole('button', { name: 'Accept all', exact: true }).first().click()
await page.getByText(/^Accepted \d+/).waitFor({ timeout: 15000 })
log('bulk accepted a pattern')

// History
await page.goto(`${base}/s/${sid}/history`)
await page.getByText('Checkpoint timeline').waitFor()
await page.getByText('Audit chain verified').waitFor({ timeout: 15000 })
await page.waitForTimeout(500)
await shot('15-history')
await page.locator('button', { hasText: 'Original' }).first().click()
await page.getByRole('button', { name: 'Back to the original' }).click()
await page.getByRole('button', { name: 'Confirm' }).click()
await page.getByText(/^Restored to K00/).waitFor({ timeout: 15000 })
const cur = await api('GET', `/sessions/${sid}/row/412`)
log(`after restore to original, row 412 pin = ${cur.values.pin}`)
await page.waitForTimeout(500)
await shot('16-history-restored')
await page.getByRole('button', { name: 'Go back' }).click()
await page.waitForTimeout(1500)
const back = await api('GET', `/sessions/${sid}/row/412`)
log(`after "Go back", row 412 pin = ${back.values.pin}`)
await page.locator('button', { hasText: 'Original' }).first().click()  // deselect: show the whole log
await page.waitForTimeout(800)
await page.getByRole('button', { name: /^Undo$/ }).first().click()
await page.getByText(/^Undid C/).waitFor()
log('undid one change from the log')
const audit = await api('GET', `/sessions/${sid}/audit/verify`)
log(`audit valid=${audit.valid} entries=${audit.entries}`)

console.log('console errors:', errors.length ? errors : 'none')
await browser.close()
