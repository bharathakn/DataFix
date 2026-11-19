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

## 6. Timings (10,200 customers + 23,060 orders)

| Step | Time |
|---|---|
| Scan both tables | ≈ 9 s |
| Plan repairs | 0.8 s |
| Apply auto batch | ≈ 1.5 s |
| Validation (re-scan + re-plan) | ≈ 5 s |
| Benchmark | ≈ 4 s |
| Export bundle (incl. highlighted XLSX) | 3.3 s |
| `datafix fix … --bench` end to end | 23.6 s |

100k-row timings: to be measured in Phase 7.
