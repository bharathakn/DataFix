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

## 2. Five-minute demo script (as built)

Start with `scripts/start_demo.sh` (add `--offline` if the Wi-Fi is unreliable or Gemini quota is low), open http://localhost:8000. Practise with a timer; `frontend/scripts/rehearse.mjs` clicks through exactly these steps and records `out/demo_backup.webm`.

| Time | Step | Click | Say (gist) |
|---|---|---|---|
| 0:00 | Hook | title slide | "Every team cleans data. Nobody can prove their cleaning didn't break something. DataFix does." |
| 0:20 | 1. Load | **Load demo dataset** | "10,200 customers and 23,060 orders with errors injected the way real pipelines create them. DataFix recognised every column from its values, not its name." |
| 0:40 | 2. Scan | **Scan 10,200 rows** → Overview | "Only 84.7% of rows are fully clean: 1,678 errors. Here's what's wrong and where." Point at the heatmap stripe. |
| 1:00 | 3. Why | sidebar **Diagnosis** | "Not just what, but why. 71 of 73 blank cities came from one mobile-app batch: 34% of that batch against 0.02% everywhere else. Branch uploads went through Excel and destroyed phone numbers." Scroll to the rules table: "Nobody wrote PIN → city. DataFix learned it from the data." |
| 1:40 | 4. Fix | **Overview → Plan repairs → Apply 1,260 high-confidence fixes** | "It only auto-applies what it can prove: 95% or more." Gauge goes 84.7% → 96.1%. |
| 2:00 | 5. Row 412 | **Repair Studio → Applied → column pin → C-10413** | "PIN 40001 has five digits. 29 real PINs are one digit away, 19 of them in Mumbai, so city alone can't decide. Only one serves this row's locality, Stock Exchange." Point at the top-3 options. |
| 2:30 | 6. Refusal | **column phone → C-10778**, then **Refused → C-11044** | "Row 777's phone was recovered from its orders. Row 1043 has two different phones in its orders, so DataFix refuses to guess." Pause here. |
| 3:00 | 7. Undo | **History → Original → Back to the original → Confirm → Go back** | "Change of mind? Jump back to any checkpoint. The original file is never touched, and the audit chain proves nobody edited the log." |
| 3:15 | 8. Chat | **Chat**: "How many customers are in Pune?", "Why did row 52 change?" | "Answers come from queries DataFix runs. Here's the query it ran." Expand "Ran 1 query". |
| 3:45 | 9. Privacy | **Privacy → Mask all high-risk** | "50 Aadhaar, PAN and phone numbers were hidden in free-text notes, each confirmed by its checksum. One click to mask, and it's undoable." |
| 4:05 | 10. Proof | **Validation**, then **Run benchmark** (≈ 6 s) | "Eight safety checks, all green: zero valid cells changed, and running DataFix again finds nothing more to auto-fix. And our own benchmark, live on your data: 160 planted errors, F1 0.99, zero false repairs." |
| 4:35 | 11. Export | **Export → Download all (ZIP)** | "Cleaned data, an Excel copy with every change highlighted and explained, the report, a tamper-evident change log, and a recipe to re-run next month." |
| 4:50 | Close | | "DataFix: find it, explain it, fix it safely, prove it." |

Tips: keep the browser at 100% zoom on a 1366×768+ projector; light theme; close the chat panel before switching pages if the screen is narrow. If Gemini is on, the chat answers in 4–9 s; offline it answers instantly from built-in patterns (Pune, row N, least confident, duplicates, undo, root causes).

## 3. Slides (6–8)

1. Title + one-line pitch.
2. Problem: dirty data costs + why current cleaning can't be trusted (one example table).
3. Approach: Detect → Diagnose → Repair → Validate → Explain → Track, with the confidence gate.
4. What's different: comparison table (trimmed from the report: rules-only tools, HoloClean, Cleanlab, OpenRefine vs DataFix).
5. Live demo.
6. Results: **measured** numbers (from [RESULTS.md](RESULTS.md)): detection F1 0.99, repair precision 100%, **false repair rate 0%**, clean rows 84.7% → 96.1%, all 8 do-no-harm checks green; 10k customers + 23k orders end to end in 20 s, 100k + 233k in 150 s on a laptop.
7. Architecture (one diagram) + "LLM never sets values; works offline".
8. Impact & roadmap: banking KYC, healthcare, e-commerce, government; drift monitoring, DB connectors, quality-gate in CI.

## 4. Judge Q&A prep

| Likely question | Answer |
|---|---|
| Isn't this just pandas cleaning? | Pandas has no idea *what's right*. We learn rules from the data (PIN→City), combine independent evidence, refuse when evidence conflicts, and prove zero valid cells changed. |
| Where do the confidence numbers come from? | Noisy-OR over independent signals, each with a reliability weight. The benchmark's calibration table shows every bucket from 0.70 up was 100% correct, so the scores are conservative; we keep auto at ≥ 0.95 on purpose. |
| What if the LLM hallucinates? | It can't change data. It only picks from whitelisted operations; the numbers come from executed code. It works fully offline. |
| How do you know repairs are correct? | Self-test benchmark: plant known errors into clean rows, measure precision, recall and false repair rate. Live, on any dataset. |
| Does it scale? | Measured on a laptop: 10k customers + 23k orders end to end (scan, repair, validation, benchmark, export) in 20 s; 100k + 233k in 150 s, with the same accuracy. Fuzzy matching uses blocking (never all row pairs), repairs work on distinct values, and the state is a change log, not copies. Chunking / Polars / DuckDB are the next step for millions of rows. |
| Is the data private? | Runs locally; raw rows never go to the LLM; PII detected with checksums and maskable before export. |
| What about non-Indian data? | Generic detectors, learned rules and benchmark are country-agnostic; Indian validators are a pluggable pack. |
| Why not just delete bad rows? | Deleting loses valid information and breaks relationships (orders). We repair cells and remap foreign keys. |
| Can the audit log be faked? | Every entry is hash-chained to the previous one; the verify endpoint recomputes the chain. |

## 5. Backup plan

- **Start:** `scripts/start_demo.sh` (one process, one port, http://localhost:8000). Use `--offline` if the Wi-Fi or Gemini quota is doubtful: every screen works without the internet (verified: the rehearsal makes zero requests outside localhost).
- **Gemini:** free tier = 20 requests/day on 2.5 Flash, then the app falls back to the lite models, then offline. Don't spend quota rehearsing. The header pill shows which mode is live.
- **Backup video:** `out/demo_backup.webm` (≈ 2 min, recorded by `frontend/scripts/rehearse.mjs` with `PAUSE=3500`). Copy it to a USB drive and your phone.
- **Backend hiccup:** sessions are saved to disk; restart `start_demo.sh` and reload the page. `curl localhost:8000/api/debug/inflight` shows what's busy.
- **UI failure:** CLI fallback `cd backend && uv run python -m datafix fix ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv --out ../out --mask notes:redact --bench`, then open `out/quality_report.html` and `out/cleaned_highlighted.xlsx`.
- **Laptop failure:** the video on USB / phone.
