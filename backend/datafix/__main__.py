"""DataFix CLI: scan, plan, fix. check / bench / apply arrive in Phase 3."""
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


def cmd_fix(args) -> int:
    import time
    from .session import Session
    t0 = time.perf_counter()
    paths = {Path(args.file).stem: args.file}
    if args.linked:
        paths[Path(args.linked).stem] = args.linked
    s = Session.from_paths(paths)
    before = s.score()
    batches = s.apply_auto()
    accepted = 0
    if args.accept_review:
        pending = [p.proposal_id for p in s.proposals.values() if p.tier == "review" and p.status == "pending"]
        accepted = s.bulk_review(pending, "accept")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in s.originals:
        s.cleaned(name, with_status=not args.no_status).to_csv(out / f"cleaned_{name}.csv", index=False)
    s.change_log().to_csv(out / "change_log.csv", index=False)
    audit = s.verify_audit()
    tiers = Counter(p.tier for p in s.proposals.values())
    status = s.row_status().value_counts().to_dict()
    print(f"quality score {before} -> {s.score()}")
    for k in batches:
        print(f"  checkpoint {k.checkpoint_id} {k.label:<32} {len(k.change_ids):>5} changes  score {k.quality_score}")
    if accepted:
        print(f"  accepted {accepted} review items")
    print(f"proposals: {dict(tiers)}")
    print(f"rows: {status}")
    print(f"audit log: {len(s.changes)} entries, chain {'valid' if audit['valid'] else 'BROKEN'}, "
          f"head {audit['head_hash'][:12]}")
    print(f"wrote {', '.join(sorted(p.name for p in out.iterdir()))} to {out}  ({time.perf_counter() - t0:.1f}s)")
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
    fx.add_argument("--no-status", action="store_true", help="omit the _datafix_status column")
    fx.set_defaults(fn=cmd_fix)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
