# Measured Results

All numbers measured on 2026-11-19 on the seeded demo data (`scripts/make_demo_data.py`, seed 42) on a laptop. Re-run the commands to reproduce. Use these numbers on slides, never the design targets.

**Caveat for honest pitching:** the demo data and the self-test benchmark use error types DataFix was built to handle. Real-world files will score lower. The benchmark's value is that it runs on *any* uploaded file and reports what it measures.

## 1. Self-test benchmark (`datafix bench`)

2,000 rows that had no detected issue, 5% of rows corrupted with one planted error each, plus 3% duplicate rows (half exact, half near). The engine runs end to end as if a reviewer accepted every suggestion.

| Seed | Planted | Detection precision | Detection recall | F1 | Repair precision | Coverage | False repairs |
|---|---|---|---|---|---|---|---|
| 42 | 160 | 100% | 98.1% | 0.991 | 100% | 77.5% | 0 |
| 7 | 160 | 100% | 99.4% | 0.997 | 100% | 79.4% | 0 |
| 123 | 160 | 100% | 98.8% | 0.994 | 100% | 85.0% | 0 |

- **False repair rate: 0.000%** on every seed (the headline trust metric).
- Uncovered errors are mostly **missing values with no evidence anywhere** (names, dates, categories), which DataFix refuses to invent, and invalid ages in wide age groups.
- Calibration: every confidence bucket (0.70–1.00) was 100% correct, so the engine is conservative. The auto threshold stays at 0.95 on purpose.
- Runtime ≈ 4 s.

```bash
cd backend && uv run python -m datafix bench ../data/demo/customers_dirty.csv --linked ../data/demo/orders.csv --seed 7
```

## 2. Demo file vs ground truth (`tests/test_detection_demo.py`, `tests/test_repair_demo.py`)

1,478 cell errors + 200 duplicate rows injected into 10,200 customers.

| Stage | Result |
|---|---|
| Detection | precision 100%, recall 99.0% (US dates with day ≤ 12 are undetectable per cell: 66%) |
| Auto-applied repairs | 1,259 correct, **0 wrong**, 0 valid cells touched, 75% of errors fixed |
| Auto + review accepted | 1,461 correct, 0 wrong, 51 age estimates, 90% coverage |
| Clean file (no errors) | 0 error flags, 0 repairs proposed |

## 3. Do-no-harm validation after auto-fix (`datafix fix`)

8 of 8 checks pass: valid cells changed 0 · schema unchanged · 120 removed rows = 120 merges · distributions stable · 0 errors introduced · 0 orphaned orders · idempotent (0 further auto-fixes) · audit chain valid.

| Dimension (% of rows free of the problem) | Before | After auto-fix |
|---|---|---|
| Completeness | 93.88 | 97.49 |
| Validity | 97.35 | 99.36 |
| Consistency | 94.77 | 100.00 |
| Uniqueness | 98.04 | 99.21 (80 near-duplicates wait for review) |
| **Clean rows** | **84.70** | **96.08** |
| Quality score (cell-weighted) | 97.63 | 99.10 |

## 4. Root cause found automatically

- 71 of 73 blank city values come from source = mobile_app and import_batch = B07 (34% of that batch vs 0.02% elsewhere).
- 123 of 140 placeholder phones come from branch_upload; all 40 Excel-notation phones come from branch_upload.
- All 33 detectable US-format dates and all 20 garbled names come from partner_api.

## 5. Privacy

All 50 planted identifiers in free-text notes found: 25 Aadhaar (Verhoeff-confirmed), 15 PAN, 10 phone. Plus structured PAN / phone / email columns.

## 6. Timings (laptop, after Phase 7 performance fixes)

Full pipeline: load → scan both tables → plan → apply all auto-fixes → do-no-harm validation (re-scan + re-plan) → root cause → benchmark (2,000 rows) → export bundle (incl. highlighted XLSX + HTML report).

| Dataset | Customers | Orders | Scan | Plan | Apply | Validate | Benchmark | Export | **Total** |
|---|---|---|---|---|---|---|---|---|---|
| Demo | 10,200 | 23,060 | 8.3 s | 0.5 s | 0.1 s | 5.3 s | 2.3 s | 2.6 s | **20.5 s** |
| 10× scale | 102,000 | 232,869 | 49.9 s | 3.1 s | 1.1 s | 49.8 s | 2.3 s | 32.2 s | **150 s** |

Both runs: all 8 do-no-harm checks pass, clean rows 84.6–84.7% → 96.05–96.08%, benchmark F1 0.99, false repair rate 0%.

Before the Phase 7 fixes the 100k run took **700 s**: applying fixes recomputed the quality score per fix and searched all issues per fix (quadratic, 352 s), date checks ran `strptime` against 19 formats per unique timestamp, age imputation and duplicate merges re-scanned whole tables per cell, and every duplicate merge copied the 100k-row table. Now: issue index + one score per batch, regex + calendar date check, cached group statistics and foreign-key index, lazy row removal, and the benchmark reuses the linked table's scan.

Reproduce: `cd backend && uv run python ../scripts/make_demo_data.py --rows 100000 --out data/demo/scale_100k`, then the timing snippet in docs/08 Phase 7.

### API (in-process, demo session)

scan 6–7 s · plan 0.8 s · apply-auto 1.8 s · validation 5.5 s · benchmark (1,000 rows) 4.5 s · export ZIP 2.7 s · rows / proposals / checkpoints / review / undo < 160 ms · chat offline < 20 ms, Gemini 4–9 s.

## Unknown dataset (user upload, 30,558 rows × 20 columns, 161k log entries) — 2026-11-20

| Operation | Before | After | Fix |
|---|---|---|---|
| History / checkpoints / undo / restore | minutes; blocked the session lock (other requests queued 750 s) | 0.2 s / 1 s | `_by_id` was a linear scan per lookup → direct index (ids are sequential) |
| `cleaned_highlighted.xlsx` | 84 s | 6 s | openpyxl → xlsxwriter (constant memory); hover notes capped at 3,000 cells (open review items first), colours on every cell |
| `change_log.csv` | 12 s | 4 s | ID column looked up once per table, not per entry; shallow `Change.to_dict` |
| Export bundle (warm validation) | 110 s | 15 s | the above |
| `GET /export/zip` from the UI | ~20 min (four clicks queued behind the lock) | 27 s cold (incl. a fresh validation), 0.03 s repeat | export files cached per session state; the button shows "Preparing ZIP…" and sends one request |
| Report preview iframe | blank (request stuck in the queue) | instant | same; spinner until the iframe loads |
