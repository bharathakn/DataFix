# 02 · Review of the Original Plan, Additions and Cuts

The original report is strong on vision, comparison and trust story. This doc lists what was missing or risky, what to add to win, and what to cut for a 24–36 h solo build.

## 1. Gaps and risks found in the original report

| # | Issue in original plan | Why it matters | Fix (adopted) |
|---|---|---|---|
| G1 | 19 innovations for one person in ~30 h | Half-built features look worse than fewer finished ones | Tiered scope in [01_FINAL_PLAN.md](01_FINAL_PLAN.md) §4 |
| G2 | "Diagnose, not fixed rules" — but PIN / phone / age repairs are all hand-coded rules | Judges will probe this exact requirement | Add **automatic functional-dependency discovery** and **disguised-missing detection**: rules learned from the data itself (§2, A1–A2) |
| G3 | Chatbot "turns question into a pandas query the backend runs" | Executing LLM-generated code = remote code execution risk; a sharp judge will ask | Gemini function calling over a **whitelisted JSON DSL**; no `eval`/`exec`/`df.query` on LLM strings |
| G4 | "PIN 40001 → suggested 400001" — no algorithm given | It's the demo's centrepiece | Digit-insertion candidate generation + reference filter + row-context agreement ([05_ENGINE_SPEC.md](05_ENGINE_SPEC.md) §5.5) |
| G5 | Duplicate handling has no merge or foreign-key policy | Deleting a customer that has orders breaks relationships | Survivorship rules + remap `orders.customer_id` to the survivor; block if conflict |
| G6 | Age imputation by group **mean** | Outlier-sensitive; also invents data | Median, guarded by group size and spread, always review tier, `_imputed` marker |
| G7 | Confidence values are "targets" with no method | "Where does 0.96 come from?" is a guaranteed question | Noisy-OR signal model + calibration table from benchmark |
| G8 | Bangalore → Bengaluru could count as "changing a valid value" | Conflicts with the 0% false repair metric | Separate repair class `standardize`; do-no-harm counts only cells with no detected issue |
| G9 | WeasyPrint PDF, Postgres, Docker, deploy | Hours of setup, zero judging value | HTML report, in-memory sessions, run locally |
| G10 | Audit log is "auditable" but not tamper-evident | "Build for trust" — prove the log wasn't edited | SHA-256 **hash-chained** change log + original-file fingerprint |
| G11 | Python 3.14 on the machine | Some scientific wheels may lag new Python releases | Use `uv` with a pinned Python 3.12 venv |
| G12 | Demo story needs specific rows (412, 52) and a 71-of-73 batch story | If the generator is random these won't exist | Seeded demo generator with guaranteed "story rows" ([09_DEMO_AND_PITCH.md](09_DEMO_AND_PITCH.md) §1) |

## 2. Additions that help win

Ranked by (judge impact) ÷ (build hours). "Verdict" is what we do in this hackathon.

| ID | Addition | What it is | Why judges care | Cost | Verdict |
|---|---|---|---|---|---|
| A1 | **Auto-discovered dependencies** | For column pairs X→Y, if ≥ 95% of X values map to one Y value, treat it as a learned rule; the 5% that disagree are violations; the majority Y is the repair candidate | Directly answers "infer, don't rely on fixed rules"; this is the core idea behind HoloClean, made usable | 2 h | **Tier A** |
| A2 | **Disguised missing values** | Placeholder tokens + frequency spikes (`9999999999` appears 140× in a phone column) | "Less-obvious data errors" from the problem statement; most tools miss these | 1 h | **Tier A** |
| A3 | **Pattern root causes** | Detect *mechanisms*: Excel scientific notation (`9.87654E+09`), encoding damage (`BengalÃ¼ru`), stray whitespace, MM/DD vs DD/MM from one source, Indian vs Western number grouping, ₹ unit mix (L / Cr) | Makes "why it was dirty" concrete and memorable | 1.5 h | **Tier B** |
| A4 | **Live self-test benchmark button** | Plant errors into the user's own clean rows, re-run, score — in the UI | Turns claims into measured numbers in front of judges | 2 h | **Tier B (top)** |
| A5 | **Refusal cards** | Every refused repair says *why*: "2 conflicting matches in orders", "group too small (n=3)" | The demo's strongest trust moment | 0.5 h | **Tier A** |
| A6 | **Hash-chained audit log** | Each change record stores `prev_hash` and `hash`; `/audit/verify` recomputes | Tamper-evident trail; cheap; very on-theme | 0.5 h | **Tier A** |
| A7 | **Idempotence check** | Run the engine on its own output: must propose 0 auto-fixes | Elegant proof of stability | 0.3 h | **Tier A** (part of do-no-harm) |
| A8 | **Highlighted Excel export** | Repaired cells green, flagged yellow, each with a cell comment holding the reason and confidence | Business users can audit in Excel; screenshots well | 1 h | **Tier A** |
| A9 | **Before/after diff grid** | Data grid toggle: original · current · diff (changed cells coloured, hover shows evidence) | The most intuitive "what changed" view | 1.5 h | **Tier B** |
| A10 | **Confidence calibration chart** | From benchmark: bucketed confidence vs. actual correctness | Shows confidence numbers mean something | 1 h | Tier B if time |
| A11 | **Quality gate CLI** | `datafix check file.csv --min-score 90` returns exit code | Shows pipeline/reproducibility story with almost no work | 0.5 h | **Tier C, likely** |
| A12 | **Per-row trust status column** | `_datafix_status` = unchanged / repaired / needs_review / estimated | Downstream users know what to trust | 0.3 h | **Tier A** |
| A13 | **Offline mode badge** | Header pill: "LLM: Gemini ✓ / offline templates" | Shows graceful degradation deliberately | 0.2 h | Tier B |
| A14 | **Column-shift detection** | Detect rows where values sit in the wrong column (email in phone column) by type mismatch across adjacent columns | Clever, rare | 1.5 h | Stretch |
| A15 | **Indian money normalisation** | `₹1.2L`, `12,00,000`, `1.2 Cr`, `Rs. 120000` → number | Distinctly Indian, demo-friendly | 0.7 h | **Tier A** |

## 3. Ideas considered and rejected

| Idea | Why not |
|---|---|
| Let the LLM propose cell values | Hallucination risk; breaks "values come only from rules, statistics and trusted references" |
| Train an ML model for repair | No time, no labelled data, hurts explainability |
| Blockchain audit trail | Hash chain gives the same tamper evidence without the gimmick |
| Polars / Spark for scale | pandas handles 100k rows in seconds; quote chunking as roadmap |
| Drift over multiple uploads | Needs several uploads to demo; low value in 5 minutes |
| Auth, multi-user approval | No judging value |

## 4. How we beat the obvious competitors in the room

Most teams will build: upload → pandas `dropna`/`fillna`/`drop_duplicates` → show a chart → maybe an LLM summary. Our differentiators, in the order the demo shows them:

1. **Root cause** ("71 of 73 blank cities came from mobile_app batch B07").
2. **Evidence-backed repair** with multiple signals and confidence.
3. **Refusal** when evidence is missing.
4. **Proof**: do-no-harm checks + live benchmark numbers.
5. **Reversibility**: time-travel undo.
6. **Privacy** with real checksum validators (Verhoeff, Luhn, GSTIN).
7. **Chat** that answers from executed queries, never invented numbers.
