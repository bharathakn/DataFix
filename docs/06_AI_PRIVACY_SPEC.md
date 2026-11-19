# 06 · Privacy Shield, Gemini and the Chatbot

## 1. Privacy shield (`privacy.py`)

### 1.1 Detection

Scan every column (sample 5,000 values, then full scan for flagged columns). Structured columns: the whole value is matched. Free-text columns (`text` type, or header like `notes`, `comments`, `remarks`, `address`): regex search inside the text, then validate each hit.

| PII type | Find | Confirm | Risk |
|---|---|---|---|
| Aadhaar | `\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b` | Verhoeff checksum | high |
| PAN | `\b[A-Z]{5}\d{4}[A-Z]\b` | 4th char in `PCHFATBLJG` | high |
| Card number | `\b(?:\d[ -]?){13,19}\b` | Luhn | high |
| Bank account | 9–18 digits in column with header `account`/`acc_no` | header hint required | high |
| GSTIN | §9 of engine spec | mod-36 check char | medium (business id) |
| Phone | Indian mobile pattern | normalised validator | medium |
| Email | email regex | — | medium |
| IFSC | IFSC regex | — | low |

Checksums drastically cut false positives (a random 12-digit number passes Verhoeff only ~10% of the time). The UI shows "validated by Verhoeff checksum" — this is a strong explainability point.

### 1.2 Masking (one click per column, applied as a checkpoint so it's undoable)

| Method | Example | Notes |
|---|---|---|
| `partial` | `98XXXXXX45`, `XXXX XXXX 1234`, `ra***@gmail.com`, `ABCPX****Q` | Keeps format |
| `redact` | `[REDACTED-AADHAAR]` | For free text, replaces only the matched span |
| `hash` | `h_3f9a1c…` (HMAC-SHA256 with a per-session salt, first 12 hex) | Same input → same token, so duplicates are still detectable |
| `drop` | column removed from export | Recorded in privacy report |

Masking changes are `Change` records with `algorithm="privacy_mask"`. They are excluded from the `valid_cells_changed` check (they're a user-requested transformation, shown separately in the report).

### 1.3 Privacy report (`privacy_report.csv`)

`column, pii_type, rows_found, in_free_text, risk, validated_by, action, method`.

## 2. What may be sent to Gemini

| Allowed | Never |
|---|---|
| Column names and semantic types | Raw rows |
| Aggregate counts, issue summaries, root-cause structs | Any value from a PII column (even masked samples) |
| Results of whitelisted tool calls, **after** PII columns are masked with `partial` | API key in any client-side code |
| A single row's change record when the user asks "why did row 52 change?" — with PII fields masked | |

Implementation: `llm.py` exposes `explain(structured) -> str`, `chat(messages, tools) -> …`, `rule_from_text(text, schema) -> RuleSpec`. Every function has a template / regex fallback. A `sanitize()` step runs on every payload before it leaves the process and drops PII-typed fields.

Config: `GEMINI_API_KEY`, `GEMINI_MODEL` (`gemini-2.5-flash`) from `.env`. Create the client with `http_options=types.HttpOptions(api_version="v1beta")`, because function calling fails on `v1` with this key. Failover order on 429/503/timeout: retry once after 1 s → `GEMINI_API_KEY_BACKUP` → offline templates. Timeout 8 s; on final error or timeout → fallback and the header badge shows "offline templates". Cache responses by payload hash (in-memory dict) so the demo is instant on repeats.

## 3. Chatbot design (`chat_tools.py` + `/chat`)

### 3.1 Principle

Gemini chooses **which** operation to run and with **what arguments**. The backend validates the arguments against the schema and runs its own code. Numbers in the answer come from tool results. No `eval`, `exec`, `df.query()` or `df.eval()` on model output.

### 3.2 Whitelisted tools (Gemini function declarations)

| Tool | Args | Returns |
|---|---|---|
| `count_rows` | `filters: Filter[]` | `{count}` |
| `list_rows` | `filters: Filter[], columns?: string[], limit ≤ 20` | table (PII masked) |
| `group_count` | `column, filters?, top ≤ 20` | table |
| `column_stats` | `column` | min/max/median/missing/distinct |
| `issue_summary` | `column?, type?` | counts |
| `explain_change` | `row_id, column?` | change records + evidence |
| `least_confident_repairs` | `limit ≤ 10` | proposals |
| `find_duplicates` | `column` | groups |
| `root_causes` | — | cause list |
| `propose_undo` | `target: {checkpoint_id} \| {column}` | `proposed_action` (not executed) |

`Filter = {column: <must exist>, op: "eq"|"neq"|"contains"|"gt"|"lt"|"is_missing"|"has_issue", value?: string}` — implemented with plain pandas boolean masks.

### 3.3 Flow

1. System prompt: role, schema (names + types), dataset summary, rules ("answer only from tool results; if unsure say so; never invent numbers").
2. Gemini returns function call(s) → validate args (pydantic) → run → feed results back → Gemini writes the final short answer.
3. Max 3 tool rounds. Reply includes `tool_calls` so the UI shows "Ran: count_rows(city = Pune) → 412" under the answer — visible proof it didn't hallucinate.

### 3.4 Offline fallback (no key / no internet)

Regex intent router covering the demo questions:
- `how many .* (from|in) (\w+)` → `count_rows(city eq X)` (try city, then state)
- `why did row (\d+) change` → `explain_change`
- `least (sure|confident)` → `least_confident_repairs`
- `duplicates? in (\w+)` → `find_duplicates`
- `undo (the )?(\w+) fix` → `propose_undo(column)`
Answer via templates. The chat still works on stage if the Wi-Fi dies.

## 4. Other LLM uses

| Use | Input | Output | Fallback |
|---|---|---|---|
| Root-cause narrative | top 5 `RootCause` structs | 3-sentence paragraph | join template sentences |
| Evidence card "plain English" line | one proposal's signals | one sentence | template from signal `detail`s |
| Plain-English rule (stretch) | user text + schema | `RuleSpec` JSON (column, op, bounds) validated by pydantic, shown for confirmation | "couldn't parse" + manual rule form |
| Report summary paragraph | scan + validation numbers | 1 paragraph | template |
