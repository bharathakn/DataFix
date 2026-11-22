// Automated rehearsal of docs/09_DEMO_AND_PITCH.md §2, recorded as a backup video.
//   scripts/start_demo.sh --offline        (in another terminal; serves UI + API on :8000)
//   cd frontend && node scripts/rehearse.mjs ../out [http://localhost:8000]
// Fails if any request leaves localhost (the demo must survive with Wi-Fi off).
import { chromium } from 'playwright-core'
import { renameSync } from 'node:fs'

const out = process.argv[2] || '../out'
const base = process.argv[3] || 'http://localhost:8000'
const PAUSE = Number(process.env.PAUSE ?? 1200)  // ms to linger on each screen so a viewer can follow
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: out, size: { width: 1440, height: 900 } }, acceptDownloads: true })
const page = await ctx.newPage()
const errors = [], external = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(String(e)))
page.on('request', (r) => { const u = new URL(r.url()); if (!['localhost', '127.0.0.1'].includes(u.hostname) && u.protocol.startsWith('http')) external.push(r.url()) })

const t0 = Date.now()
let last = t0
const step = (s) => { const now = Date.now(); console.log(`${((now - t0) / 1000).toFixed(1).padStart(6)}s  (+${((now - last) / 1000).toFixed(1)}s)  ${s}`); last = now }
const linger = (ms = PAUSE) => page.waitForTimeout(ms)
const nav = (label) => page.locator('nav').getByRole('link', { name: label }).click()

// 1. load demo, column types
await page.goto(base)
await linger()
await page.getByRole('button', { name: 'Load demo dataset' }).click()
await page.getByText('Check the column types').waitFor({ timeout: 30000 })
step('1 demo loaded: column types detected')
await linger()

// 2. scan -> overview
await page.getByRole('button', { name: /^Scan / }).click()
await page.getByText('Next: plan repairs').waitFor({ timeout: 60000 })
step('2 scanned: overview with warnings + heatmap')
await linger(PAUSE * 1.5)
await page.getByText('Where the errors are').scrollIntoViewIfNeeded()
await linger()

// 3. root cause
await nav('Diagnosis')
await page.getByText(/of \d+ blank city/).first().waitFor({ timeout: 30000 })
step('3 diagnosis: mobile_app + B07 story, learned rules')
await linger(PAUSE * 1.5)
await page.getByText('Rules DataFix learned from your data').scrollIntoViewIfNeeded()
await linger()

// 4. plan + apply
await nav('Overview')
await page.getByRole('button', { name: 'Plan repairs' }).click()
await page.getByRole('button', { name: /^Apply .* high-confidence fixes/ }).waitFor({ timeout: 60000 })
step('4a plan ready (tiers)')
await linger()
await page.getByRole('button', { name: /^Apply .* high-confidence fixes/ }).click()
await page.getByText('Repairs applied').waitFor({ timeout: 60000 })
step('4b auto-fixes applied: clean rows 82.8% -> 94.9%')
await linger(PAUSE * 1.5)

// 5. row 412
await nav('Repair Studio')
await page.getByRole('button', { name: /^Applied/ }).click()
await page.getByLabel('Filter by column').selectOption('pin')
await page.locator('[data-pid]', { hasText: 'C-10413' }).first().click()
await page.getByText(/serves the post office 'Stock Exchange/).waitFor({ timeout: 15000 })
step('5 row 412: 40001 -> 400001 with evidence')
await linger(PAUSE * 2)

// 6. recovery + refusal
await page.getByLabel('Filter by column').selectOption('phone')
await page.locator('[data-pid]', { hasText: 'C-10778' }).first().click()
await page.getByText(/matching orders records agree|orders has phone/).first().waitFor({ timeout: 15000 })
step('6a row 777: phone recovered from orders')
await linger()
await page.getByRole('button', { name: /^Refused/ }).click()
await page.getByLabel('Filter by column').selectOption('phone')
await page.locator('[data-pid]', { hasText: 'C-10644' }).first().click()
await page.getByText('DataFix refused to guess').waitFor({ timeout: 15000 })
step('6b row 643: refused (conflicting phones)')
await linger(PAUSE * 2)

// 7. undo timeline
await nav('History')
await page.locator('button', { hasText: 'Original' }).first().click()
await page.getByRole('button', { name: 'Back to the original' }).click()
await page.getByRole('button', { name: 'Confirm' }).click()
await page.getByText(/^Restored to K00/).waitFor({ timeout: 15000 })
step('7a restored to the original')
await linger()
await page.getByRole('button', { name: 'Go back' }).click()
await page.waitForTimeout(1500)
step('7b back to the latest checkpoint')

// 8. chat
await page.getByRole('button', { name: 'Chat', exact: true }).click()
for (const q of ['How many customers are in Pune?', 'Why did row 52 change?']) {
  const n = await page.locator('[data-testid="assistant-turn"]').count()
  await page.getByLabel('Chat message').fill(q)
  await page.getByLabel('Chat message').press('Enter')
  await page.waitForFunction((k) => document.querySelectorAll('[data-testid="assistant-turn"]').length > k, n, { timeout: 30000 })
  step(`8 chat: ${q} -> ${(await page.locator('[data-testid="assistant-turn"]').last().innerText()).split('\n')[0].slice(0, 70)}`)
  await linger()
}
await page.getByLabel('Close chat').click()

// 9. privacy
await nav('Privacy')
await page.getByRole('button', { name: /Mask all high-risk/ }).click()
await page.getByText(/^Masked [\d,]+ high-risk values/).waitFor({ timeout: 30000 })
step('9 privacy: Aadhaar/PAN in notes masked')
await linger()

// 10. proof
await nav('Validation')
await page.getByText(/\d \/ 8 passed/).waitFor({ timeout: 60000 })
step(`10a validation: ${await page.getByText(/\d \/ 8 passed/).innerText()}`)
await linger()
await page.getByRole('button', { name: 'Run benchmark' }).click()
await page.getByText('False repair rate', { exact: true }).waitFor({ timeout: 90000 })
await page.getByText('False repair rate', { exact: true }).scrollIntoViewIfNeeded()
step('10b benchmark run live')
await linger(PAUSE * 2)

// 11. export
await nav('Export')
await page.getByText(/do-no-harm checks passed|check\(s\) failed/).waitFor({ timeout: 60000 })
const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.getByRole('button', { name: /Download all/ }).click()])
step(`11 export: ${dl.suggestedFilename()}`)
await linger()

const video = page.video()
await ctx.close()
const target = `${out}/demo_backup.webm`
renameSync(await video.path(), target)
await browser.close()
console.log(`\nvideo: ${target}`)
console.log('external requests:', external.length ? external : 'none (works with Wi-Fi off)')
console.log('console errors:', errors.length ? errors : 'none')
if (external.length || errors.length) process.exit(1)
