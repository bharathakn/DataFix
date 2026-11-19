"""DataFix CLI: scan, plan, fix, check (quality gate), bench (self-test). Recipe replay (`apply`) is a stretch item."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .ingest import load_path
from .scan import ScanResult, scan_table


def _print(res: ScanResult, top: int) -> None:
    print(f"\n== {res.table}: {res.n_rows:,} rows × {len(res.columns)} columns ==")
    print("column types:")
    for c, i in res.columns.items():
        print(f"  {c:<18} {i.semantic_type:<10} conf {i.type_confidence:.2f}  blanks {i.null_count}")
    print(f"\nquality score: {res.quality_score}")
    print("issues by type:")
    for t, n in sorted(res.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<18} {n:>6}")
    sparse = [i.column for i in res.issues if i.type == "sparse_column"]
    if sparse:
        print(f"optional (sparse) columns: {', '.join(sparse)}")
    if res.rules:
        print("rules learned / checked:")
        for r in res.rules:
            print(f"  {r.rule_id} {r.description:<40} support {r.support:>6}  conf {r.confidence:.3f}  "
                  f"violations {r.violations}")
    print("top columns:")
    per_col = Counter({c: sum(v.values()) for c, v in res.by_column.items()})
    for c, n in per_col.most_common(top):
        print(f"  {c:<18} {n:>6}  {res.by_column[c]}")
    print(f"timings (ms): {res.timings_ms}")


def cmd_scan(args) -> int:
    results = []
    for path in [args.file] + ([args.linked] if args.linked else []):
        lt = load_path(path)
        res = scan_table(lt.df, Path(path).name)
        results.append(res)
        _print(res, args.top)
    if args.json:
        out = [{"table": r.table, "quality_score": r.quality_score, "counts": r.counts,
                "columns": {c: i.to_dict() for c, i in r.columns.items()},
                "rules": [x.to_dict() for x in r.rules], "issues": [i.to_dict() for i in r.issues]} for r in results]
        Path(args.json).write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
        print(f"\nwrote {args.json}")
    return 0


def cmd_plan(args) -> int:
    from .planner import plan_tables, summarize
    paths = {Path(args.file).stem: args.file}
    if args.linked:
        paths[Path(args.linked).stem] = args.linked
    tables, scans, props, timings = plan_tables(paths)
    summ = summarize(props)
    print(f"{len(props)} proposals  {timings}")
    print("tiers:", summ["tiers"])
    for k, n in summ["by_class"].items():
        print(f"  {k:<28} {n:>5}")
    reasons = Counter((p.refusal_reason or "").split(":")[0].split(" for ")[0][:70]
                      for p in props if p.tier in ("refused", "flag") and p.refusal_reason)
    print("why refused / flagged:")
    for r, n in reasons.most_common(12):
        print(f"  {n:>5}  {r}")
    for spec in filter(None, (args.rows or "").split(",")):
        row = int(spec)
        for p in (p for p in props if p.row_id == row and p.table == Path(args.file).stem):
            print(f"\nrow {row} · {p.column}: '{p.original_value}'  [{p.tier}] {p.repair_class}/{p.algorithm}")
            if p.refusal_reason:
                print(f"   refused/flagged: {p.refusal_reason}")
            for c in p.candidates:
                print(f"   → {c.value!r}  {c.confidence:.0%}")
                for sgn in c.signals:
                    print(f"       {'✗' if sgn.conflicting else '✓'} {sgn.detail}")
    if args.json:
        Path(args.json).write_text(json.dumps([p.to_dict() for p in props], indent=1, ensure_ascii=False))
        print(f"\nwrote {args.json}")
    return 0


def _paths(args) -> dict[str, str]:
    paths = {Path(args.file).stem: args.file}
    if getattr(args, "linked", None):
        paths[Path(args.linked).stem] = args.linked
    return paths


def cmd_fix(args) -> int:
    import time
    from .export import export_bundle
    from .session import Session
    t0 = time.perf_counter()
    s = Session.from_paths(_paths(args))
    batches = s.apply_auto()
    if args.accept_review:
        pending = [p.proposal_id for p in s.proposals.values() if p.tier == "review" and p.status == "pending"]
        print(f"  accepted {s.bulk_review(pending, 'accept')} review items")
    for spec in args.mask or []:
        col, _, method = spec.partition(":")
        k = s.mask_column(col, method or "partial")
        print(f"  {k.label}: {len(k.change_ids)} cells")
    if args.bench:
        b = s.run_benchmark()
        print(f"benchmark: detection F1 {b['detection']['f1']:.3f}, repair precision {b['repair']['precision']:.3f}, "
              f"false repair rate {b['repair']['false_repair_rate']:.4%}")
    val = s.validate()
    s.diagnose()
    files = export_bundle(s, args.out)
    d0, d1 = val["dimensions_before"], val["dimensions_after"]
    for k in batches:
        print(f"  checkpoint {k.checkpoint_id} {k.label:<32} {len(k.change_ids):>5} changes")
    print(f"clean rows {d0['clean_rows']}% -> {d1['clean_rows']}%   quality score {val['score_before']} -> {val['score_after']}")
    print("do-no-harm: " + ", ".join(f"{c['name']} {'PASS' if c['passed'] else 'FAIL'}" for c in val["checks"]))
    print(f"needs review: {val['unresolved']}")
    print(f"wrote {len(files) - 1} files + {files['zip'].name} to {Path(args.out)}  ({time.perf_counter() - t0:.1f}s)")
    return 0 if val["passed"] else 2


def cmd_check(args) -> int:
    from .validate import dimensions
    df = load_path(args.file).df
    df = df[[c for c in df.columns if not c.startswith("_datafix")]]  # our own status column is not data
    res = scan_table(df, Path(args.file).name)
    dims = dimensions(res.issues, res.n_rows)
    failures = []
    if res.quality_score < args.min_score:
        failures.append(f"quality score {res.quality_score} < {args.min_score}")
    for spec in args.min or []:
        name, _, limit = spec.partition("=")
        if name not in dims:
            print(f"unknown dimension {name!r}; choose from {sorted(dims)}")
            return 2
        if dims[name] < float(limit):
            failures.append(f"{name} {dims[name]}% < {limit}%")
    print(f"{Path(args.file).name}: score {res.quality_score} | " + " | ".join(f"{k} {v}%" for k, v in dims.items()))
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("PASS")
    return 0


def cmd_bench(args) -> int:
    from .session import Session
    s = Session.from_paths(_paths(args))
    r = s.run_benchmark(sample_rows=args.rows, error_rate=args.rate, seed=args.seed)
    det, rep = r["detection"], r["repair"]
    print(f"{r['injected']} errors planted in {r['sample_rows']} clean rows (seed {r['seed']}, {r['duration_ms']} ms)")
    print(f"detection  precision {det['precision']:.3f}  recall {det['recall']:.3f}  F1 {det['f1']:.3f}")
    print(f"repair     precision {rep['precision']:.3f} (auto tier {rep['auto_precision']:.3f})  coverage "
          f"{rep['coverage']:.3f}  correct {rep['correct']}  wrong {rep['wrong']}  estimates {rep['estimates']}")
    print(f"false repairs {rep['false_repairs']}  (rate {rep['false_repair_rate']:.4%} of clean cells)")
    for t in r["by_error_type"]:
        print(f"  {t['type']:<20} planted {t['injected']:>4}  detected {t['detected']:>4}  repaired {t['repaired_correctly']:>4}")
    print("calibration: " + ", ".join(f"{c['bucket']} predicted {c['predicted']:.2f} actual {c['actual']:.2f} (n={c['n']})"
                                      for c in r["calibration"]))
    if args.json:
        Path(args.json).write_text(json.dumps(r, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="datafix")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="detect issues and print a summary")
    s.add_argument("file")
    s.add_argument("--linked", help="linked table, e.g. orders.csv")
    s.add_argument("--json", help="write full results to this JSON file")
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(fn=cmd_scan)
    pl = sub.add_parser("plan", help="propose repairs with confidence tiers")
    pl.add_argument("file")
    pl.add_argument("--linked")
    pl.add_argument("--rows", help="comma-separated row numbers to explain, e.g. 412,1043")
    pl.add_argument("--json")
    pl.set_defaults(fn=cmd_plan)
    fx = sub.add_parser("fix", help="apply high-confidence repairs, write cleaned data + change log")
    fx.add_argument("file")
    fx.add_argument("--linked")
    fx.add_argument("--out", default="datafix_output")
    fx.add_argument("--accept-review", action="store_true", help="also accept the top candidate of review items")
    fx.add_argument("--mask", action="append", help="privacy mask COLUMN:METHOD (partial|redact|hash|drop)")
    fx.add_argument("--bench", action="store_true", help="run the self-test benchmark and include it in the report")
    fx.set_defaults(fn=cmd_fix)
    ck = sub.add_parser("check", help="quality gate: exit 1 if the file is below the thresholds")
    ck.add_argument("file")
    ck.add_argument("--min-score", type=float, default=0.0)
    ck.add_argument("--min", action="append", help="dimension threshold, e.g. clean_rows=95 or validity=99")
    ck.set_defaults(fn=cmd_check)
    bn = sub.add_parser("bench", help="self-test: plant known errors in clean rows and measure the engine")
    bn.add_argument("file")
    bn.add_argument("--linked")
    bn.add_argument("--rows", type=int, default=2000)
    bn.add_argument("--rate", type=float, default=0.05)
    bn.add_argument("--seed", type=int, default=42)
    bn.add_argument("--json")
    bn.set_defaults(fn=cmd_bench)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
