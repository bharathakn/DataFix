// Screenshot every page (light, plus a few in dark) for visual review of the theme.
//   cd frontend && node scripts/ui_shots.mjs <outdir> [http://localhost:8000]
import { chromium } from 'playwright-core'

const out = process.argv[2] || '/tmp'
const base = process.argv[3] || 'http://localhost:8000'
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
const shot = async (name, full = true) => { await page.waitForTimeout(600); await page.screenshot({ path: `${out}/${name}.png`, fullPage: full }) }
const nav = (label) => page.locator('nav').getByRole('link', { name: label }).click()

await page.goto(base)
await shot('01_upload')
await page.getByRole('button', { name: 'Load demo dataset' }).click()
await page.getByText('Check the column types').waitFor()
await shot('02_columns')
await page.getByRole('button', { name: /^Scan / }).click()
await page.getByText('Next: plan repairs').waitFor({ timeout: 90000 })
await shot('03_overview_scanned')
await nav('Diagnosis'); await page.getByText('71 of 73 blank city').first().waitFor(); await shot('04_diagnosis')
await nav('Privacy'); await page.getByRole('heading', { name: 'Personal data found' }).waitFor(); await shot('05_privacy')
await nav('Overview'); await page.getByRole('button', { name: 'Plan repairs' }).click()
await page.getByRole('button', { name: /^Apply .* high-confidence fixes/ }).click({ timeout: 90000 })
await page.getByText('Repairs applied').waitFor({ timeout: 90000 })
await shot('06_overview_repaired')
await nav('Repair Studio'); await page.waitForTimeout(1500); await shot('07_repair', false)
await nav('Validation'); await page.getByText(/\d \/ 8 passed/).waitFor({ timeout: 90000 }); await shot('08_validation')
await nav('History'); await page.getByText('Checkpoint timeline').waitFor(); await shot('09_history')
await nav('Export'); await page.waitForTimeout(1500); await shot('10_export')
await page.getByRole('button', { name: 'Chat', exact: true }).click(); await page.waitForTimeout(500); await shot('11_chat', false)
await page.getByLabel('Close chat').click()
await page.getByRole('button', { name: 'Toggle dark mode' }).click()
await nav('Overview'); await page.getByText('Repairs applied').waitFor(); await shot('12_dark_overview')
await nav('Repair Studio'); await page.waitForTimeout(1500); await shot('13_dark_repair', false)
await page.getByRole('button', { name: 'Toggle dark mode' }).click()
await page.setViewportSize({ width: 390, height: 844 }); await nav('Overview'); await shot('14_mobile_overview', false)
await browser.close()
console.log('console errors:', errors.length ? errors : 'none')
