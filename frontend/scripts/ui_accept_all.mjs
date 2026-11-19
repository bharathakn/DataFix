// Repair Studio "Accept all" for the review queue: warning dialog -> confirm -> one checkpoint -> Undo all.
//   cd frontend && node scripts/ui_accept_all.mjs <outdir> [http://localhost:8000]
import { chromium } from 'playwright-core'

const out = process.argv[2] || '/tmp'
const base = process.argv[3] || 'http://localhost:8000'
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(String(e)))
const log = (s) => console.log('✓', s)

await page.goto(base)
await page.getByRole('button', { name: 'Load demo dataset' }).click()
await page.getByRole('button', { name: /^Scan / }).click()
await page.getByRole('button', { name: 'Plan repairs' }).click({ timeout: 90000 })
await page.getByRole('button', { name: /^Apply .* high-confidence fixes/ }).click({ timeout: 60000 })
await page.getByText('Repairs applied').waitFor({ timeout: 60000 })
await page.locator('nav').getByRole('link', { name: 'Repair Studio' }).click()

const btn = page.getByRole('button', { name: /^Accept all [\d,]+$/ })
const label = await btn.innerText()
log(`button: ${label}`)
await btn.click()
const dlg = page.getByRole('dialog')
await dlg.getByText('likely wrong fixes').waitFor({ timeout: 15000 })
const confirm = dlg.getByRole('button', { name: /^Accept all [\d,]+$/ })
if (!(await confirm.isDisabled())) throw new Error('confirm must be disabled until the checkbox is ticked')
await page.keyboard.press('a')  // review shortcut must not fire behind the dialog
await page.screenshot({ path: `${out}/accept_all_dialog.png` })
log('dialog shows warning; confirm disabled until checkbox ticked')
await dlg.getByRole('checkbox').check()
const t0 = Date.now()
await confirm.click()
const toast = page.getByText(/^Accepted [\d,]+ suggestions as checkpoint K\d+/)
await toast.waitFor({ timeout: 120000 })
log(`${await toast.innerText()} (${((Date.now() - t0) / 1000).toFixed(1)} s)`)
await page.screenshot({ path: `${out}/accept_all_done.png` })
await page.getByRole('button', { name: 'Undo all' }).click()
await page.getByRole('button', { name: /^Accept all [\d,]+$/ }).waitFor({ timeout: 60000 })
log(`after Undo all: ${await page.getByRole('button', { name: /^Accept all [\d,]+$/ }).innerText()}`)
await browser.close()
console.log('console errors:', errors.length ? errors : 'none')
if (errors.length) process.exit(1)
