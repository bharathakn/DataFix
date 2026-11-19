"""DataFix CLI. Phase 1 ships `scan`; fix / check / bench / apply arrive in later phases."""
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="datafix")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="detect issues and print a summary")
    s.add_argument("file")
    s.add_argument("--linked", help="linked table, e.g. orders.csv")
    s.add_argument("--json", help="write full results to this JSON file")
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(fn=cmd_scan)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
