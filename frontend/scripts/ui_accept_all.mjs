// Bulk decisions: review-queue Accept all (warning -> one checkpoint -> Undo all), Reject all on Patterns /
// Refused (warning -> no cell changed -> Undo all), and Privacy "Keep as is" / "Keep all unmasked".
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

// Patterns tab carries both bulk buttons for the whole review queue
await page.getByRole('button', { name: /^Patterns/ }).click()
await page.getByRole('button', { name: /^Reject all [\d,]+$/ }).waitFor()
log(`patterns: ${await page.getByRole('button', { name: /^Accept all [\d,]+$/ }).innerText()} + ${await page.getByRole('button', { name: /^Reject all [\d,]+$/ }).innerText()}`)

// Refused: Reject all with warning, then Undo all puts them back
await page.getByRole('button', { name: /^Refused/ }).click()
const rej = page.getByRole('button', { name: /^Reject all [\d,]+$/ })
await rej.waitFor()
const before = await rej.innerText()
await rej.click()
const rd = page.getByRole('dialog')
await rd.getByText('cells will stay blank or invalid').waitFor()
await page.screenshot({ path: `${out}/reject_all_refused.png` })
await rd.getByRole('checkbox').check()
await rd.getByRole('button', { name: /^Reject all/ }).click()
const rt = page.getByText(/^Rejected [\d,]+ refused items; no cell was changed/)
await rt.waitFor({ timeout: 60000 })
log(await rt.innerText())
await page.getByText('Nothing here').waitFor()
await page.getByRole('button', { name: 'Undo all' }).click()
await page.getByRole('button', { name: before }).waitFor({ timeout: 30000 })
log(`refused after Undo all: ${before}`)

// Privacy: keep one column unmasked, undo; keep-all dialog warns about high-risk IDs
await page.locator('nav').getByRole('link', { name: 'Privacy' }).click()
await page.getByRole('button', { name: 'Keep as is' }).first().click()
await page.getByText('kept unmasked', { exact: true }).first().waitFor()
log('privacy: column kept unmasked')
await page.getByRole('button', { name: 'Undo', exact: true }).first().click()
await page.getByText('kept unmasked', { exact: true }).waitFor({ state: 'detached' })
await page.getByRole('button', { name: /^Keep all unmasked/ }).click()
await page.getByRole('dialog').getByText(/DPDP Act/).waitFor()
await page.screenshot({ path: `${out}/privacy_keep_all.png` })
await page.getByRole('dialog').getByRole('button', { name: 'Keep all unmasked' }).click()
await page.getByText(/^Kept \d+ columns unmasked/).waitFor()
log(`privacy: ${await page.getByText(/^Kept \d+ columns unmasked/).innerText()}; mask-all now ${await page.getByRole('button', { name: /^Mask all high-risk/ }).innerText()}`)

await browser.close()
console.log('console errors:', errors.length ? errors : 'none')
if (errors.length) process.exit(1)
