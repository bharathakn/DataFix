# 09 · Demo Dataset, Demo Script and Pitch

## 1. Demo dataset (`scripts/make_demo_data.py`, seed 42)

### 1.1 Clean base

`customers_clean.csv` — 10,000 rows:

| Column | Generation |
|---|---|
| `customer_id` | `C-10001`… |
| `name` | Indian first + last names (include `Mohammad`, etc.) |
| `gender` | M/F |
| `age` | depends on `occupation` (student 18–24, engineer 23–45, teacher 28–60, retired 60–80, …) so group-median imputation is meaningful |
| `occupation` | 8 values |
| `email` | from name + domain (gmail, yahoo, outlook, company) |
| `phone` | valid 10-digit, starts 6–9 |
| `locality`, `pin`, `city`, `district`, `state` | sampled from ~40 real PIN/city/state rows taken from the PIN reference (Mumbai 400001…, Bengaluru 560001…, Pune 411001…, Chennai, Kolkata, Delhi, Hyderabad, Ahmedabad, Jaipur, Lucknow …), weighted so Pune has a nice round-ish count |
| `signup_date` | DD/MM/YYYY across 2022–2026 |
| `annual_income` | plain integer rupees |
| `pan` | valid-format PAN (4th char P) |
| `source` | `web_form` 40%, `mobile_app` 25%, `branch_upload` 20%, `partner_api` 15% |
| `import_batch` | `B01`–`B12` by date |
| `created_at` | ISO timestamp |
| `notes` | short free text; mostly harmless |

`orders.csv` — ~25,000 rows: `order_id, customer_id, email, phone, order_date, quantity, unit_price, total`. Phones/emails copied from the clean customer (this is what phone recovery uses).

### 1.2 Injected errors (each tied to a root cause so Diagnosis has real stories)

| Error | Count | Injected where | Root cause the app should find |
|---|---|---|---|
| Blank city | 73 | 71 in `mobile_app` + `B07`, 2 random | "71 of 73 blank cities come from mobile_app batch B07" |
| Other missing values | ~400 | random across email/age/phone | — |
| Disguised missing | 140 phones = `9999999999`, 30 emails `test@test.com` | mostly `branch_upload` | placeholder entry |
| Exact duplicates | 120 | random | — |
| Near duplicates | 80 | name typo / email case / phone formatting | — |
| City misspellings | 150 | `Banglore`, `Bengaluru ` (space), `Pune.`, `Hydrabad`, `Chenai` | manual entry |
| City aliases | 60 | `Bombay`, `Bangalore`, `Madras`, `Calcutta` | — |
| PIN↔city violations | 40 | city swapped so it disagrees with PIN | learned rule `pin → city` |
| Invalid emails | 100 | missing dot / `@@` / space | — |
| Invalid ages | 50 | negative, 0, 150 | — |
| Mixed date formats | 50 | `partner_api` writes MM/DD/YYYY | "partner_api writes US-style dates" |
| 5-digit PINs | 30 | one digit dropped | — |
| 5-digit phones | 30 | truncated | recoverable from orders |
| Excel sci-notation phones | 40 | `branch_upload` | "branch uploads went through Excel" |
| Encoding damage | 20 names | `partner_api` (`JosÃ©`-style on accented names, or `â€™` apostrophes) | UTF-8 read as Latin-1 |
| Income unit mix | 200 | `₹1.2L`, `12,00,000`, `1.5 Cr` | — |
| Planted PII in notes | 25 Aadhaar (Verhoeff-valid), 15 PAN, 10 phones | `notes` | privacy shield |
| Orders total mismatch | 30 | `total ≠ qty × price` | cross-field |
| Real outliers (NOT errors) | 5 incomes 40–80 L | random | must be flagged only, never changed |

All injections recorded in `truth.json`: `{row_id, column, clean_value, dirty_value, error_type}`.

### 1.3 Story rows (guaranteed by the generator)

| Row | Setup | Expected behaviour |
|---|---|---|
| 412 (`C-10413`) | city Mumbai, locality "Stock Exchange", PIN `40001` | 29 valid PINs one digit away, 19 in Mumbai; only `400001` serves Stock Exchange → confidence ≥ 0.95 |
| 52 | city `Banglore`, PIN 560001, state Karnataka | → `Bengaluru`; evidence: similarity 91%, PIN 560001, state; chatbot "Why did row 52 change?" |
| 777 | phone `98765` (5 digits), orders for this customer have one distinct phone | Recovered from orders, confidence ~0.92 |
| 1043 | phone missing, orders for this customer contain **two different phones** | **Refused**: "2 conflicting phones in orders — DataFix won't guess" |
| 2001 | age missing, occupation `retired`, Pune | Imputed group median, tier review, marked **estimated** |
| 2002 | age missing, occupation `astronaut` (only 2 rows) | **Refused**: "group too small (n=2)" |
| 3000 | income `₹80,00,000` (real outlier) | Flagged as anomaly, **unchanged** |

## 2. Five-minute demo script

Practise to time. Speak to the problem, not the tech.

| Time | Step | Say (gist) | Show |
|---|---|---|---|
| 0:00 | Hook | "Every team cleans data. Nobody can prove their cleaning didn't break something. DataFix does." | Title slide → app |
| 0:20 | 1. Load demo | "10,000 customers + 25,000 orders, with errors injected the way real pipelines create them." | Click demo; column types auto-detected (point at `col_7` → PIN if you rename one) |
| 0:40 | 2. Scan | "Score 61. Here's what's wrong and where." | Overview: KPIs, warnings, heatmap stripe at batch B07 |
| 1:00 | 3. Root cause | "Not just *what* — *why*. 71 of 73 blank cities came from one mobile-app batch. Branch uploads went through Excel and destroyed phone numbers." | Diagnosis page; learned rules table: "nobody wrote PIN→City, DataFix learned it" |
| 1:40 | 4. Auto-fix | "Only fixes it can prove — 95%+ confidence." | Plan → Apply; timeline fills with checkpoints; score jumps |
| 2:00 | 5. Row 412 | "PIN 40001 has 5 digits. 29 real PINs are one digit away, 19 of them in Mumbai — city alone can't decide. Only one serves this row's locality, Stock Exchange." | Evidence card with signals narrowing 29 → 19 → 1 |
| 2:30 | 6. Recovery + refusal | "Row 777's phone recovered from orders. Row 1043 has two different phones in orders — DataFix **refuses to guess**." | Refused tab, refusal banner — pause here |
| 3:00 | 7. Undo | "Change of mind? Jump back to any checkpoint. The original file is never touched." | Restore → forward |
| 3:15 | 8. Chat | "Ask in English. Answers come from executed queries — here's the query it ran." | "How many customers are in Pune?", "Why did row 52 change?" |
| 3:45 | 9. Privacy | "25 Aadhaar numbers hidden in free-text notes, confirmed by the Verhoeff checksum. One click to mask." | Privacy page → mask |
| 4:05 | 10. Proof | "Zero valid cells changed. And here's our own benchmark, run live." | Validation: checks green → Run benchmark → precision/recall/false repair rate |
| 4:35 | 11. Export | "Cleaned data, Excel with every change highlighted and explained, report, tamper-evident change log, and a recipe to re-run next month." | Download ZIP, open XLSX |
| 4:50 | Close | "DataFix: find it, explain it, fix it safely, prove it." | |

## 3. Slides (6–8)

1. Title + one-line pitch.
2. Problem: dirty data costs + why current cleaning can't be trusted (one example table).
3. Approach: Detect → Diagnose → Repair → Validate → Explain → Track, with the confidence gate.
4. What's different: comparison table (trimmed from the report: rules-only tools, HoloClean, Cleanlab, OpenRefine vs DataFix).
5. Live demo.
6. Results: **measured** benchmark numbers + 10k/100k timings (from `docs/RESULTS.md`).
7. Architecture (one diagram) + "LLM never sets values; works offline".
8. Impact & roadmap: banking KYC, healthcare, e-commerce, government; drift monitoring, DB connectors, quality-gate in CI.

## 4. Judge Q&A prep

| Likely question | Answer |
|---|---|
| Isn't this just pandas cleaning? | Pandas has no idea *what's right*. We learn rules from the data (PIN→City), combine independent evidence, refuse when evidence conflicts, and prove zero valid cells changed. |
| Where do the confidence numbers come from? | Noisy-OR over independent signals, each with a reliability weight; thresholds are tuned on the benchmark, and the calibration chart shows predicted vs. actual accuracy. |
| What if the LLM hallucinates? | It can't change data. It only picks from whitelisted operations; the numbers come from executed code. It works fully offline. |
| How do you know repairs are correct? | Self-test benchmark: plant known errors into clean rows, measure precision, recall and false repair rate. Live, on any dataset. |
| Does it scale? | 10k rows in X s, 100k in Y s on a laptop (show measured). Vectorised pandas, blocking for fuzzy matching; chunking and Polars on the roadmap. |
| Is the data private? | Runs locally; raw rows never go to the LLM; PII detected with checksums and maskable before export. |
| What about non-Indian data? | Generic detectors, learned rules and benchmark are country-agnostic; Indian validators are a pluggable pack. |
| Why not just delete bad rows? | Deleting loses valid information and breaks relationships (orders). We repair cells and remap foreign keys. |
| Can the audit log be faked? | Every entry is hash-chained to the previous one; the verify endpoint recomputes the chain. |

## 5. Backup plan

- Wi-Fi down → offline LLM templates + bundled PIN reference; badge shows "offline".
- Backend crash → sessions are pickled; restart and reload the page.
- Laptop failure → backup video on USB + phone.
- Something breaks mid-demo → CLI: `python -m datafix fix data/demo/customers_dirty.csv --out out/` and open `report.html`.
