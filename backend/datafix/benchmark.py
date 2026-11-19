"""Self-test benchmark (docs/05_ENGINE_SPEC.md §8): plant known errors in clean rows, run the engine, score it.

Works on any dataset: ground truth is the user's own rows that had no detected issue.
"""
import random
import time
from collections import Counter, defaultdict

import pandas as pd

from . import validators as v
from .ingest import LoadedTable
from .knowledge import CITY_ALIASES

ROW = "__row__"
REVERSE_ALIAS = {}
for _alias, _canon in CITY_ALIASES.items():
    REVERSE_ALIAS.setdefault(_canon, _alias.title())
CATEGORY_TYPES = {"category", "city", "state", "district", "locality"}
MISSING_TYPES = {"email", "phone", "city", "age", "pin", "category", "name", "date", "money", "state", "district"}


def _typo(rng: random.Random, x: str) -> str | None:
    if len(x) < 5:
        return None
    i = rng.randrange(1, len(x) - 1)
    op = rng.choice(["delete", "swap", "replace"])
    if op == "delete":
        return x[:i] + x[i + 1:]
    if op == "swap" and x[i] != x[i + 1]:
        return x[:i] + x[i + 1] + x[i] + x[i + 2:]
    ch = rng.choice("aeiou" if x[i].lower() not in "aeiou" else "rstnl")
    return x[:i] + ch + x[i + 1:]


def _indian_commas(n: int) -> str:
    s = str(n)
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


class Injector:
    """Each method returns the dirty value, or None if it does not apply to this cell."""

    def __init__(self, rng: random.Random, df: pd.DataFrame, types: dict[str, str]):
        self.rng, self.df, self.types = rng, df, types
        self.cities = [c for c, t in types.items() if t == "city"]
        self.city_values = sorted({x for c in self.cities for x in df[c] if x.strip()})

    def options(self, row: int) -> list[tuple[str, str]]:
        out = []
        for col, t in self.types.items():
            x = self.df.at[row, col]
            if not x.strip():
                continue
            if t in MISSING_TYPES:
                out.append(("missing", col))
            if t in ("phone", "email"):
                out.append(("placeholder", col))
            if t in CATEGORY_TYPES and len(x) >= 5:
                out.append(("typo", col))
            if t == "city" and x in REVERSE_ALIAS:
                out.append(("alias", col))
            if t == "city" and any(tt == "pin" for tt in self.types.values()) and len(self.city_values) > 2:
                out.append(("rule_violation", col))
            if t == "name":
                out.append(("case_space", col))
            if t == "date" and v.date_families(x) & {"dmy"}:
                out.append(("us_date", col))
            if t == "age":
                out.append(("invalid_age", col))
            if t == "phone" and v.is_phone(x):
                out += [("truncated_phone", col), ("excel_phone", col)]
            if t == "pin" and v.is_pin_format(x):
                out.append(("pin_digit_dropped", col))
            if t == "email" and v.is_email(x):
                out.append(("email_typo", col))
            if t == "money" and x.strip().isdigit() and int(x) >= 1000:
                out.append(("money_format", col))
        return out

    def make(self, kind: str, col: str, x: str) -> str | None:
        rng = self.rng
        if kind == "missing":
            return ""
        if kind == "placeholder":
            return "9999999999" if self.types[col] == "phone" else "test@test.com"
        if kind == "typo":
            return _typo(rng, x)
        if kind == "alias":
            return REVERSE_ALIAS[x]
        if kind == "rule_violation":
            others = [c for c in self.city_values if v.norm_key(c) != v.norm_key(x)]
            return rng.choice(others) if others else None
        if kind == "case_space":
            return x.upper() if rng.random() < 0.5 else x + "  "
        if kind == "us_date":
            d = v.parse_date(x, prefer="dmy")
            return d.strftime("%m/%d/%Y") if d and d.day != d.month else None
        if kind == "invalid_age":
            return rng.choice(["-5", "150", "0", "999"])
        if kind == "truncated_phone":
            return v.normalize_phone(x)[:5]
        if kind == "excel_phone":
            p = v.normalize_phone(x)
            return f"{p[0]}.{p[1:6]}E+09"
        if kind == "pin_digit_dropped":
            i = rng.randrange(1, 6)
            return x[:i] + x[i + 1:]
        if kind == "email_typo":
            local, dom = x.split("@", 1)
            return rng.choice([f"{local}@{dom.replace('.', '', 1)}", f"{local}@@{dom}", f"{local} @{dom}"])
        if kind == "money_format":
            n = int(x)
            return f"₹{n / 1e5:g}L" if n % 1000 == 0 else _indian_commas(n)
        return None


def _same(col_type: str, a: str, b: str) -> bool:
    if col_type == "phone":
        return v.normalize_phone(a) == v.normalize_phone(b)
    if col_type == "email":
        return a.strip().casefold() == b.strip().casefold()
    if col_type == "money":
        pa, pb = v.parse_money(a), v.parse_money(b)
        return pa is not None and pa == pb
    return a.strip() == b.strip()


def inject(df: pd.DataFrame, types: dict[str, str], error_rate: float, dup_rate: float,
           seed: int) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    rng = random.Random(seed)
    df = df.reset_index(drop=True).copy()
    inj = Injector(rng, df, types)
    n = len(df)
    rows = rng.sample(range(n), min(n, round(n * error_rate)))
    truth = []
    for r in rows:
        opts = inj.options(r)
        rng.shuffle(opts)
        for kind, col in opts:
            dirty = inj.make(kind, col, df.at[r, col])
            if dirty is not None and dirty != df.at[r, col]:
                truth.append({"row": r, "column": col, "clean": df.at[r, col], "dirty": dirty, "type": kind})
                df.at[r, col] = dirty
                break
    corrupted = {t["row"] for t in truth}
    id_col = next((c for c, t in types.items() if t == "id" and df[c].is_unique), None)
    name_col = next((c for c, t in types.items() if t == "name"), None)
    email_col = next((c for c, t in types.items() if t == "email"), None)
    dups, extra = [], []
    pool = [r for r in range(n) if r not in corrupted]
    for k, src in enumerate(rng.sample(pool, min(len(pool), round(n * dup_rate)))):
        row = df.loc[src].copy()
        if id_col:
            row[id_col] = f"BENCH-{k + 1:05d}"
        near = k % 2 == 1
        if near and email_col and row[email_col]:
            row[email_col] = row[email_col].upper()
        elif near and name_col and len(row[name_col]) > 4:
            j = rng.randrange(1, len(row[name_col]) - 1)
            row[name_col] = row[name_col][:j] + row[name_col][j + 1:]
        extra.append(row)
        dups.append({"row": n + k, "duplicate_of": src, "type": "near_duplicate" if near else "duplicate"})
    if extra:
        df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
    return df, truth, dups


def run_benchmark(session, sample_rows: int = 2000, error_rate: float = 0.05, dup_rate: float = 0.03,
                  seed: int = 42) -> dict:
    from .session import Session  # local: session imports this module's siblings

    t0 = time.perf_counter()
    main = session.main
    scan = session.scans[main]
    types = {c: i.semantic_type for c, i in scan.columns.items()}
    bad_rows = {i.row_id for i in scan.issues if i.row_id is not None}
    clean_rows = [r for r in session.originals[main].index if r not in bad_rows]
    rng = random.Random(seed)
    picked = sorted(rng.sample(clean_rows, min(sample_rows, len(clean_rows))))
    base = session.originals[main].loc[picked]
    dirty, truth, dups = inject(base, types, error_rate, dup_rate, seed)

    tables = {main: LoadedTable(dirty, "benchmark", "benchmark")}
    for n in session.originals:
        if n != main:
            tables[n] = LoadedTable(session.current(n), n, session.files[n]["sha256"])
    b = Session(tables, main, session.thresholds)
    b.scan()
    b.plan()
    b.apply_auto()
    auto_ids = {p.proposal_id for p in b.proposals.values() if p.status == "applied"}
    for p in list(b.proposals.values()):
        if p.tier == "review" and p.status == "pending" and p.table == main:
            b.review(p.proposal_id, "accept")

    # ---- detection
    error_types = {"missing", "disguised_missing", "invalid_format", "inconsistent", "fd_violation", "crossfield"}
    s0 = b.scans[main]
    flagged = {(i.row_id, i.column) for i in s0.issues if i.type in error_types and i.row_id is not None}
    flagged_dups = {i.row_id for i in s0.issues if i.type in ("duplicate", "near_duplicate")}
    truth_cells = {(t["row"], t["column"]): t for t in truth}
    truth_dups = {d["row"]: d for d in dups}
    tp = len(flagged & set(truth_cells)) + len(flagged_dups & set(truth_dups))
    n_flags = len(flagged) + len(flagged_dups)
    n_true = len(truth_cells) + len(truth_dups)
    precision = tp / n_flags if n_flags else 1.0
    recall = tp / n_true if n_true else 1.0

    # ---- repair
    per_type = defaultdict(Counter)
    for t in truth:
        per_type[t["type"]]["injected"] += 1
        per_type[t["type"]]["detected"] += (t["row"], t["column"]) in flagged
    for d in dups:
        per_type[d["type"]]["injected"] += 1
        per_type[d["type"]]["detected"] += d["row"] in flagged_dups
    correct = wrong = estimates = false_repairs = 0
    auto_correct = auto_wrong = 0
    calib = defaultdict(lambda: [0.0, 0, 0])  # bucket -> [sum conf, n, n correct]
    est_errors = []
    for c in b.applied_changes(main):
        p = b.proposals.get(c.proposal_id or "")
        is_auto = p is not None and p.proposal_id in auto_ids
        if c.column == ROW:
            ok = c.row_id in truth_dups
            correct, wrong = correct + ok, wrong + (not ok)
            per_type[truth_dups[c.row_id]["type"] if ok else "false_merge"]["repaired_correctly"] += ok
            if is_auto:
                auto_correct, auto_wrong = auto_correct + ok, auto_wrong + (not ok)
            continue
        t = truth_cells.get((c.row_id, c.column))
        if t is None:
            if c.original_value.strip() and not c.reason.startswith("filled from duplicate"):
                false_repairs += 1
            continue
        if p and p.repair_class == "impute":
            estimates += 1
            if v.is_number(c.new_value) and v.is_number(t["clean"]):
                est_errors.append(abs(float(c.new_value) - float(t["clean"])))
            continue
        ok = _same(types.get(c.column, ""), c.new_value, t["clean"])
        correct, wrong = correct + ok, wrong + (not ok)
        if is_auto:
            auto_correct, auto_wrong = auto_correct + ok, auto_wrong + (not ok)
        per_type[t["type"]]["repaired_correctly"] += ok
        bucket = "0.95–1.00" if c.confidence >= 0.95 else "0.90–0.95" if c.confidence >= 0.9 else \
            "0.80–0.90" if c.confidence >= 0.8 else "0.70–0.80"
        calib[bucket][0] += c.confidence
        calib[bucket][1] += 1
        calib[bucket][2] += ok

    clean_cells = dirty.shape[0] * dirty.shape[1] - len(truth_cells)
    return {
        "sample_rows": len(base), "injected": n_true, "seed": seed, "error_rate": error_rate, "dup_rate": dup_rate,
        "detection": {"precision": round(precision, 4), "recall": round(recall, 4),
                      "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0},
        "repair": {
            "precision": round(correct / (correct + wrong), 4) if correct + wrong else 1.0,
            "auto_precision": round(auto_correct / (auto_correct + auto_wrong), 4) if auto_correct + auto_wrong else 1.0,
            "coverage": round((correct + wrong + estimates) / n_true, 4) if n_true else 0.0,
            "correct": correct, "wrong": wrong, "estimates": estimates,
            "estimate_mean_abs_error": round(sum(est_errors) / len(est_errors), 2) if est_errors else None,
            "false_repairs": false_repairs,
            "false_repair_rate": round(false_repairs / clean_cells, 6) if clean_cells else 0.0,
        },
        "by_error_type": [{"type": k, "injected": c["injected"], "detected": c["detected"],
                           "repaired_correctly": c["repaired_correctly"]} for k, c in sorted(per_type.items())],
        "calibration": [{"bucket": k, "predicted": round(s / n, 3), "actual": round(ok / n, 3), "n": n}
                        for k, (s, n, ok) in sorted(calib.items())],
        "duration_ms": int((time.perf_counter() - t0) * 1000),
    }
