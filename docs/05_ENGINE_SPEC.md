# 05 · Engine Specification

Every algorithm in the `datafix` package. Each rule here is implementable without asking a question.

## 1. Global rules

1. **Never change a cell that has no detected issue.** Every `Change` must reference a `RepairProposal` whose `issue_ids` include an issue on that exact cell (or row, for dedupe).
2. **Values come only from** deterministic transforms, the dataset's own statistics or learned rules, linked tables, and reference data. Never from the LLM.
3. **Outlier ≠ error.** Anomalies are `flag` tier only, never auto-repaired.
4. **Prefer refusing to guessing.** Refusal is a first-class result with a reason.
5. Deterministic: all randomness seeded (`seed=42` default).

## 2. Ingestion (`ingest.py`)

- CSV: sniff encoding with `charset-normalizer`; delimiter with `csv.Sniffer`; `pd.read_csv(dtype=str, keep_default_na=False, na_filter=False)`.
- Excel: `openpyxl` via `pd.read_excel(dtype=str)`; first sheet unless user picks. Also record if cells were numeric with scientific format (feeds root cause A3).
- JSON: `pd.json_normalize` on a list of records; values cast to `str`.
- Add `_rid` (0..n-1). Strip nothing on load; whitespace is a detectable issue.
- Size guard: > 200k rows → load, but detection and plan run in chunks of 50k.

## 3. Column type detection (`coltypes.py`)

For each column, sample up to 2,000 non-empty values. For each semantic type compute the match ratio with its validator. Pick the type with the highest ratio if ≥ 0.6; break ties with header hints (`email`, `mail`, `phone`, `mobile`, `pin`, `pincode`, `zip`, `dob`, `date`, `age`, `pan`, `gst`, `aadhaar`, `ifsc`, `amount`, `income`, `price`, `city`, `state`, `name`, `id`). Header hints add +0.15 but can't create a type with ratio < 0.4 — this is how "col_7" still gets recognised as a PIN.

| Semantic type | Validator (match = value is a plausible instance, even if dirty) |
|---|---|
| email | contains `@` and a dot after it |
| phone | after removing `+91`, `0`, spaces, `-`, `()`: 10 digits starting 6–9; or 5–12 digit numeric strings in a mostly-phone column |
| pin | 6 digits, first digit 1–9 (also 5-digit numerics in a mostly-PIN column) |
| date | `dateutil.parser.parse` succeeds with no extra text |
| age | integer 0–120 (column-level: mostly in 0–120 and header hint or name) |
| money | number with optional `₹`/`Rs`, commas, `L`/`lakh`/`Cr`/`crore`/`K` |
| pan / gstin / aadhaar / ifsc | see §9 validators |
| id | ≥ 95% unique, short alphanumeric |
| category | distinct / non-null < 0.05 or distinct ≤ 50 |
| name | mostly alphabetic words, 1–4 tokens, title case |
| text | average length > 30 or many spaces |
| number | parses as float |

## 4. Detectors (`detect/`)

Severity weights feed the quality score. A cell's weight is the **max** over its issues (no double counting).

| Type | Weight | Detector | Logic |
|---|---|---|---|
| `missing` | 0.7 | missing | empty string or whitespace only |
| `disguised_missing` | 0.7 | disguised | (a) token list: `na, n/a, null, none, nil, -, --, ?, unknown, not available, 0000000000, 9999999999, 1234567890, test@test.com, abc@xyz.com, 1900-01-01, 01/01/1900, 1970-01-01`; (b) frequency spike: in a column with distinct ratio > 0.5, a value whose count > max(10, 20 × median count) |
| `duplicate` | 1.0 | duplicates | exact duplicate after excluding `_rid` and the ID column; keep the first |
| `near_duplicate` | 1.0 | duplicates | blocking key = normalised email or phone or (first 3 chars of name + PIN); inside each block, pairwise RapidFuzz `token_sort_ratio` over name/email/phone/city; mean ≥ 90 → candidate pair |
| `invalid_format` | 0.4 | formats | value fails its column's validator but is not missing (e.g. `arjun@gmail`, 5-digit phone, `40001`, `-5` age, `31/02/2024`) |
| `inconsistent` | 0.4 | consistency | same entity, different representation: case/whitespace variants, alias groups (`Bombay/Mumbai`, `Bangalore/Bengaluru`, `Madras/Chennai`, `Calcutta/Kolkata`, `Gurgaon/Gurugram`, `Mohd/Mohammad`), mixed date formats in one column, mixed money units |
| `fd_violation` | 0.8 | fd | see §4.1 |
| `crossfield` | 0.8 | crossfield | `total ≈ quantity × unit_price` (±1%); `order_date ≥ signup_date`; GSTIN chars 1–2 = state code of `state`; GSTIN chars 3–12 = `pan` if both present; DOB vs age disagree by > 1 |
| `anomaly` | 0.2 | anomalies | numeric: robust z = 0.6745·(x − median)/MAD > 3.5; multivariate (≥ 3 numeric cols): IsolationForest contamination 0.01. **Flag only.** |
| `pii` | 0 (separate) | privacy | see [06_AI_PRIVACY_SPEC.md](06_AI_PRIVACY_SPEC.md) |

### 4.0 Implementation notes (Phase 1)

- **Sparse columns:** a column ≥ 30% empty is treated as optional by design (`sparse_column`, weight 0, one column-level issue) instead of flagging every blank cell (e.g. `pan`, `notes`).
- **Age** is valid in 1–120 (0 is flagged); make configurable when user rules land.
- **Aliases** are flagged only when both forms occur in the column; a column that consistently says "Bangalore" (India Post's district name) is not an error.
- **Spelling** compares rare values against frequent values (≥ 20× more common) and against known aliases, using OSA edit distance ≤ 1 for ≤ 6 chars, ≤ 2 (+ ratio ≥ 80) for ≤ 12 chars, else ratio ≥ 85. `Banglore` → `Bangalore` (alias) → `Bengaluru`.
- **Internal double spaces** are flagged only when the single-spaced form also occurs (official names like "Infotech  Park (Hinjawadi)" exist).
- **Mojibake** covers cp1252 (`â€™`, `Ã©`), latin-1 C1 control characters and U+FFFD.
- **Near duplicates:** a pair qualifies only if all strict fields (date, number, money, age, pin, phone, id, PAN, GSTIN, Aadhaar, IFSC) are equal after normalisation and at most 2 text fields differ, each with similarity ≥ 85. Mean similarity ≥ 92. Blocks larger than 50 rows (placeholders) are skipped. This removed 812 false "near duplicates" between different orders of the same customer.
- **FD violations are suppressed** when (a) the row's X cell is itself suspect, or (b) a rule Z→Y with confidence ≥ this rule's agrees with the row's Y value. Example: PIN 400001 spans Mumbai and Raigarh districts, but locality→district (100%) explains it.
- Anomalies: robust z on log scale for skewed positive columns; IsolationForest not implemented (24h cut).

### 4.1 Functional dependency discovery (the "learned rules" feature)

For every ordered pair of columns (X, Y) where X and Y are `category`, `pin`, `name`-like-city, or `id` types and X is not unique:

1. Take rows where both are non-missing and valid. Normalise Y (casefold, strip, alias-canonicalise).
2. For each X value with support ≥ 3 rows, find the majority Y and its share.
3. `fd_confidence` = (rows agreeing with their group's majority) / (rows in groups with support ≥ 3).
4. Accept X→Y as a learned rule if `fd_confidence ≥ 0.95` and ≥ 20 groups (or ≥ 50% of rows covered).
5. Rows disagreeing with their group majority become `fd_violation` issues on Y, with `meta = {rule, majority_value, group_size, majority_share}`.

Expected learned rules on demo data: `pin → city`, `pin → state`, `city → state`, `customer_id(orders) → email`. They appear in the Diagnosis page as "Rules DataFix learned from your data" with support/confidence and an on/off toggle.

## 5. Repairs (`repair/`, `planner.py`)

The planner turns issues into `RepairProposal`s. One proposal per (row, column); dedupe proposals are per duplicate group.

### 5.1 Confidence model (`confidence.py`)

Each candidate gathers `Signal`s. Combine with noisy-OR, then apply conflicts:

```
conf = 1 − Π_i (1 − reliability_i × score_i)          over supporting signals
conf = conf × Π_j (1 − reliability_j × score_j)        over conflicting signals
conf = min(conf, cap_for_repair_class)
```

| Signal | Reliability | Score |
|---|---|---|
| `deterministic_transform` (same value, new format) | 0.99 | 1.0 |
| `reference_pin` (India Post) | 0.97 | 1.0 if one district, 0.7 if PIN spans districts |
| `fd_majority` | 0.9 | rule confidence × majority share of the group |
| `linked_table_match` | 0.92 | 1.0 if exactly one distinct value, else conflicting |
| `string_similarity` | 0.7 | RapidFuzz ratio / 100 |
| `vocab_frequency` | 0.5 | candidate frequency share in column (target is a common value, original is rare) |
| `alias_dictionary` | 0.95 | 1.0 |
| `row_context` (other fields in the row agree, e.g. city matches PIN) | 0.85 | 1.0 / 0.0 |
| `group_statistic` (age median) | 0.6 | 1 − IQR/40 |

Caps: `impute` 0.85 (never auto), `dedupe_merge` near-duplicate 0.94 (never auto), exact duplicate 0.99.

Tiers (defaults, adjustable, tuned with benchmark): `auto ≥ 0.95`, `review 0.70–0.95`, `flag < 0.70`. `refused` = no candidate could be generated, or a hard guard tripped; carries `refusal_reason`.

### 5.1a Implementation notes (Phase 2A)

- Candidates are **ranked on uncapped confidence**, then capped. Otherwise extra evidence can't break a tie between candidates that all hit the 0.99 cap.
- **Ambiguity:** if the runner-up is within 0.05 of the top candidate, the top one is capped at 0.85 (review) with a conflicting "ambiguous" signal naming the runner-up.
- **Learned rules vote:** every learned rule X→Y whose X cell in the row is trusted votes for its group majority (`fd_majority`). A suggestion the rules disagree with gets a conflicting signal.
- **Locality matching** is fuzzy on letters and exact on numbers ("Sector 12" ≠ "Sector 21"), after stripping India Post suffixes (SO, B.O, H.O, GPO, PO).
- **Age imputation:** `group_statistic` reliability 0.85, score `1 − 0.15·IQR/15`, so a valid estimate always lands in review (≈0.72–0.85), never auto. Groups need n ≥ 5 and IQR ≤ 15; the grouping column is the category column with the tightest weighted IQR, and only if it beats the overall IQR by 20%.
- **Near-duplicate merges** use a `record_match` signal (0.95): the pair already matched on every strict field. Capped at 0.94, so always review.
- **Linked-table recovery:** joins are same-named ID columns, then email columns. Exactly one distinct valid value → candidate (`linked_table_match`, plus `records_agree` if ≥ 2 records, plus `prefix_match` if the broken value's digits appear in it). Two or more distinct values → refused with the masked values listed.
- Cross-field totals: candidate = quantity × price, `crossfield_rule` weighted by how often the rule holds; review tier, since quantity or price could be the wrong field.

### 5.2 Repair catalogue

| Repair class | Handles | Candidate generation | Refuses when |
|---|---|---|---|
| `normalize` | whitespace, case, phone formatting (`+91 98765-43210` → `9876543210`), Excel sci-notation phone (`9.87654E+09` only if mantissa has all 10 digits, else refuse), unambiguous dates → column's dominant format, money (`₹1.2L` → `120000`, `1.2 Cr` → `12000000`, `12,00,000` → `1200000`) | deterministic transform | ambiguous date (`03/04/2025`) with no column evidence → review with both readings |
| `standardize` | alias / variant spellings of the same entity | dominant canonical form in the column (from alias dictionary, else most frequent variant) | two canonical forms tie |
| `correct` (spelling) | rare category value near a frequent one (`Banglore`) | RapidFuzz `process.extract` against column vocabulary of values with count ≥ 5; top 3 | best similarity < 80, or top two candidates within 3 points and no context signal |
| `correct` (fd) | `fd_violation` | group majority value | group majority share < 0.8 |
| `recover` (PIN) | 5-digit / invalid PIN | §5.5 | 0 or ≥ 2 candidates agree with row context |
| `recover` (address from PIN) | missing city/district/state with valid PIN | reference lookup, then own data FD | PIN not in reference and no FD group |
| `recover` (PIN from address) | missing PIN with city+district | only if the district has exactly one PIN in own data | almost always refuses → shows "refused: district has 14 PINs" (good demo moment) |
| `recover` (phone) | missing / invalid phone | linked table (orders) rows with same `customer_id`, else same email; distinct valid phones | 0 matches, or ≥ 2 distinct phones (conflict) |
| `recover` (email) | missing email | linked table by `customer_id` | same as phone |
| `impute` (age) | missing / invalid age | median age of rows sharing the best grouping column (try `occupation`, `city`, `department`, `role` — pick the one with lowest within-group IQR) | group n < 5, or IQR > 15, or no grouping column |
| `dedupe_merge` | duplicates, near duplicates | survivor = most complete row (fewest issues), tie → earliest `created_at`, tie → lowest `_rid`; fill survivor's missing cells from the others only when they don't conflict | conflicting non-empty values in key fields (email, phone) → review shows side-by-side |
| `none` | anomalies, crossfield without a determinable side | — | always flag with explanation |

Dedupe and relationships: when a row is merged away, every `orders.customer_id` pointing to it is remapped to the survivor (each remap is a `Change` in the same checkpoint). If the merged-away ID has orders and the two customers' emails differ, refuse.

### 5.3 Checkpoint batching for auto-apply

`apply-auto` creates one checkpoint per class, in this order: `Formats normalised` → `Values standardised` → `Duplicates merged` → `Spelling & learned-rule fixes` → `PIN / address recovered` → `Contacts recovered`. After each checkpoint, store the quality score. Demo result: 313 / 91 / 121 / 249 / 103 / 383 changes.

### 5.4 Status column

Cleaned export adds `_datafix_status` per row, highest priority first: `needs_review` (a pending review/flag/refused proposal on the row), `estimated` (an applied `impute`), `repaired` (≥ 1 applied change), else `unchanged`. Demo after auto-fix: 8,629 unchanged · 1,046 repaired · 405 needs review.

### 5.5 PIN digit recovery (demo row 412: `40001` → `400001`)

1. Input invalid PIN `p` (5 digits, or 7 digits, or one digit typo).
2. Candidates: for 5 digits, insert each digit 0–9 at each of 6 positions (≤ 60); for 7 digits, delete each position (7); for 6-digit not-in-reference, substitute each position (54).
3. Keep candidates that exist in the PIN reference.
4. For each, signals: `row_context` = reference district/state matches the row's city/state (casefolded, alias-aware: city "Bengaluru" ↔ district "Bangalore"); `locality_match` (reliability 0.95) = the row's `locality` is a post office served by that PIN in the reference; `fd_majority` if own data has the PIN with that city.
5. Exactly one candidate with row-context **and** locality agreement → confidence ≈ 0.97 → auto/review. Several agree → top 3, review. None agree → refused: "no valid PIN within one digit matches Mumbai".

Verified on the full India Post directory: `40001` has 29 valid PINs within one digit, 19 of them in Mumbai (`400010`–`400019`, `400021`, …). City alone cannot decide; locality "Stock Exchange" is served only by `400001`. Demo line: *"29 valid PINs are one digit away, 19 are in Mumbai, only one serves Stock Exchange."*

Locality matching must normalise office names: the directory writes `Stock Exchange SO`, `Pune H.O`, `Kothimir B.O`, `Mumbai GPO`, while the API (and our demo data) writes `Stock Exchange`. Strip `SO / S.O / BO / B.O / HO / H.O / GPO / EDO` suffixes, casefold, then fuzzy-match (RapidFuzz ≥ 90). District names also differ (`BENGALURU URBAN` vs `Bangalore`), so city ↔ district comparison is alias- and fuzzy-aware.

## 6. Root-cause diagnosis (`diagnose.py`)

### 6.1 Source lift analysis

Context columns = low-cardinality columns that look like provenance: name contains `source`, `batch`, `channel`, `import`, `file`, `system`, `created`, or any `category` column with 2–30 values; date columns bucketed by day/week.

For each (issue type, column) with ≥ 10 issues and each context column C with value v:

```
share  = issues in group v / total issues of this kind
rate_v = issues in group v / rows in group v
lift   = rate_v / overall rate
```

Report a cause if `share ≥ 0.5` and `lift ≥ 3`. Sentence template: "**{issues_in_group} of {total}** {issue label} in **{column}** come from **{C} = {v}** ({rate_v:.0%} of its rows vs {overall:.0%} elsewhere). Likely cause: the {v} pipeline does not populate {column}." Suggested fix template by issue type.

### 6.2 Pattern causes

| Pattern | Detection | Explanation shown |
|---|---|---|
| Excel scientific notation | `^\d(\.\d+)?E\+\d+$` in phone/id columns | "Numbers were opened in Excel and saved as scientific notation, which loses digits." |
| Encoding damage | `Ã`, `Â`, `â€` sequences; fix via `value.encode('latin-1').decode('utf-8')` round trip | "File saved in UTF-8 but read as Latin-1." |
| Date locale mix | column has both `dd>12` and `mm>12` evidence, grouped by source | "Source X writes MM/DD/YYYY; others write DD/MM/YYYY." |
| Truncation | values cut at a fixed length across many rows | "A field length limit truncated values." |
| Whitespace / case | ≥ 5% of values differ from their stripped/casefolded form | "Manual entry without trimming." |
| Unit mix | money column with both `L`/`Cr` suffix and plain numbers | "Amounts entered in lakh/crore notation by some users." |
| Placeholder | disguised missing cluster | "Form required a value, so users typed a placeholder." |

Gemini may rephrase the top causes into one paragraph (input: the structured causes only).

## 7. Validation (`validate.py`)

### 7.1 Quality score

```
Q = 100 × (1 − Σ_cells max_weight(cell) / N_cells)
```
Row-level issues (duplicates) count every cell of the row once. Reported before, after each checkpoint, and final.

### 7.2 Do-no-harm checks (all must be green before export; export still allowed with a warning)

| Check | Pass condition |
|---|---|
| `valid_cells_changed` | cells changed that had no issue = **0** |
| `schema_unchanged` | same columns, same order (added `_datafix_status` is separate) |
| `row_count_explained` | rows removed = applied dedupe merges |
| `distribution_stable` | numeric: |median change| < 5% and KS statistic < 0.1 (scipy-free implementation fine); categorical: no new categories except canonical forms, top-5 unchanged |
| `no_new_errors` | re-scan current data: zero issues on cells that were clean originally |
| `referential_integrity` | every `orders.customer_id` exists in customers |
| `idempotent` | planning on current data yields 0 `auto` proposals |
| `audit_chain_valid` | hash chain verifies |

## 8. Self-test benchmark (`benchmark.py`)

1. Take rows with **no issues** from the current dataset (sample up to 2,000) = ground truth.
2. Inject errors (seeded), recording truth `(row, col, clean, dirty, type)`:
   missing 5%, disguised placeholder 1%, duplicates 3% (exact and with small typos), spelling typos in category columns 2% (one edit), city alias swaps 1%, dates reformatted 2%, ages negative / > 120 1%, phones truncated to 5 digits 1%, PIN with one digit dropped 1%, emails with domain dot removed 1%, Excel sci-notation phones 0.5%, Aadhaar/PAN planted in notes 1%.
3. Run scan → plan → apply **auto + review top candidate** (simulating acceptance) on the copy.
4. Score:
   - detection precision / recall / F1 (cell level)
   - repair precision = correct applied / applied; coverage = errors with an applied repair / injected
   - **false repair rate** = clean cells changed / clean cells
   - per error type table
   - calibration: buckets 0.7–0.8, 0.8–0.9, 0.9–0.95, 0.95–1.0 → predicted mean vs. actual accuracy
5. Report the numbers that come out. Never hard-code targets.

Also: `scripts/make_demo_data.py` writes `truth.json`, so `python -m datafix bench --truth data/demo/truth.json` scores against the real demo injections.

## 9. Validators (`validators/`)

| Name | Rule |
|---|---|
| email | `^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$` |
| phone (IN) | normalised 10 digits, first digit 6–9 |
| pin | `^[1-9][0-9]{5}$` and (if reference loaded) present in reference |
| pan | `^[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]$` |
| gstin | `^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$` + mod-36 check character + state code 01–38 |
| aadhaar | 12 digits, first digit 2–9, **Verhoeff** checksum valid |
| ifsc | `^[A-Z]{4}0[A-Z0-9]{6}$` |
| card | 13–19 digits, **Luhn** valid |
| date | `dateutil` parse; reject impossible (Feb 30); detect format string per value |
| age | integer 0–120 (configurable 18–65 via user rule) |
| money | parse rules in §5.2 |

## 10. Recipe (`recipe.py`)

Records approved steps as data, not row IDs, so it replays on a new file:
```json
{"version": 1, "column_types": {"col_7": "pin"},
 "steps": [
   {"op": "normalize", "column": "phone", "params": {"format": "10digit"}},
   {"op": "standardize", "column": "city", "params": {"map": {"Bangalore": "Bengaluru", "Bombay": "Mumbai"}}},
   {"op": "fd_repair", "rule": "pin->city"},
   {"op": "dedupe", "keys": ["email", "phone"], "survivorship": "most_complete"}],
 "thresholds": {"auto": 0.95, "review": 0.70}}
```
`python -m datafix apply recipe.json new.csv` runs scan → recipe steps → auto tier only → writes outputs.

## 11. CLI (`__main__.py`)

```
python -m datafix scan  FILE [--linked orders.csv]          # print issues, score
python -m datafix fix   FILE [--linked …] --out DIR         # auto tier only, write ZIP contents
python -m datafix check FILE --min-score 90                 # exit 1 if below
python -m datafix bench FILE [--truth truth.json]
python -m datafix apply RECIPE FILE --out DIR
```
