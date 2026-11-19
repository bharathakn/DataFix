"""Export bundle (docs/01_FINAL_PLAN.md §4.8): cleaned data, highlighted Excel, report, logs, recipe, ZIP."""
import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

from .recipe import build_recipe

ROW = "__row__"
FILLS = {"repaired": PatternFill("solid", fgColor="C6EFCE"), "estimated": PatternFill("solid", fgColor="BDD7EE"),
         "review": PatternFill("solid", fgColor="FFEB9C"), "masked": PatternFill("solid", fgColor="E4DFEC")}
TEMPLATES = Path(__file__).parent / "templates"


def _cell_marks(s, table: str) -> dict[tuple[int, str], tuple[str, str]]:
    """(row, col) -> (style, comment) for the highlighted workbook."""
    marks: dict[tuple[int, str], tuple[str, str]] = {}
    for p in s.proposals.values():
        if p.table != table or p.column == ROW or p.status != "pending" or p.tier not in ("review", "flag", "refused"):
            continue
        why = p.refusal_reason or (f"suggested '{p.candidates[0].value}' ({p.candidates[0].confidence:.0%})"
                                   if p.candidates else p.tier)
        marks[(p.row_id, p.column)] = ("review", f"DataFix: needs review. {why}")
    for c in s.applied_changes(table):
        if c.column == ROW or c.algorithm == "privacy_drop":
            continue
        p = s.proposals.get(c.proposal_id or "")
        style = "masked" if c.algorithm == "privacy_mask" else (
            "estimated" if p and p.repair_class == "impute" else "repaired")
        note = f"DataFix: '{c.original_value}' → '{c.new_value}'. {c.reason}. Confidence {c.confidence:.0%}. " \
               f"Source: {c.source}. Change {c.change_id}."
        marks[(c.row_id, c.column)] = (style, note)
    return marks


def write_highlighted_xlsx(s, path: Path, table: str | None = None) -> Path:
    table = table or s.main
    df = s.cleaned(table)
    marks = _cell_marks(s, table)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Cleaned data")
    bold = Font(bold=True)
    header = []
    for name in df.columns:
        cell = WriteOnlyCell(ws, value=name)
        cell.font = bold
        header.append(cell)
    ws.append(header)
    cols = list(df.columns)
    for row_id, values in zip(df.index, df.itertuples(index=False, name=None)):
        out = []
        for col, val in zip(cols, values):
            mark = marks.get((row_id, col))
            if mark is None:
                out.append(val)
                continue
            cell = WriteOnlyCell(ws, value=val)
            cell.fill = FILLS[mark[0]]
            cell.comment = Comment(mark[1][:1000], "DataFix")
            out.append(cell)
        ws.append(out)
    legend = wb.create_sheet("Legend")
    legend.append(["Colour", "Meaning"])
    for style, text in [("repaired", "Repaired by DataFix (hover for before value, reason, confidence)"),
                        ("estimated", "Estimated value (group median) – treat as an estimate"),
                        ("review", "Needs human review (suggestion or reason in the comment)"),
                        ("masked", "Masked by the privacy shield")]:
        c = WriteOnlyCell(legend, value=style)
        c.fill = FILLS[style]
        legend.append([c, text])
    wb.save(path)
    return path


def _report_data(s) -> dict:
    main = s.main
    scan = s.scans[main]
    val = s.validation or s.validate()
    causes = s.causes if s.causes is not None else s.diagnose()
    if not s.privacy:
        s.privacy_scan()
    by_type = Counter(i.type for i in scan.issues if i.row_id is not None and i.type != "anomaly")
    by_col: dict[str, Counter] = defaultdict(Counter)
    for i in scan.issues:
        if i.row_id is not None and i.column:
            by_col[i.column][i.type] += 1
    applied = [p for p in s.proposals.values() if p.status == "applied" and p.table == main]
    groups: dict[tuple, list] = defaultdict(list)
    for p in applied:
        groups[(p.repair_class, p.algorithm)].append(p)
    repairs = []
    for (cls, algo), ps in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        srcs = Counter()
        for p in ps:
            for cid in p.meta.get("change_ids", [])[:1]:
                srcs[s._by_id(cid).source] += 1
        repairs.append({"class": cls, "algorithm": algo, "count": len(ps),
                        "avg_conf": sum(p.confidence for p in ps) / len(ps),
                        "auto": sum(1 for p in ps if p.tier == "auto"),
                        "source": srcs.most_common(1)[0][0] if srcs else ""})
    unresolved = [p for p in s.proposals.values() if p.table == main and p.status == "pending"
                  and p.tier in ("review", "flag", "refused")]
    unresolved.sort(key=lambda p: ({"refused": 0, "review": 1, "flag": 2}[p.tier], p.row_id))
    id_col = next((c for c, i in scan.columns.items() if i.semantic_type == "id"
                   and i.distinct >= 0.95 * len(s.originals[main])), None)
    max_type = max(by_type.values()) if by_type else 1
    audit = s.verify_audit()
    tiers = Counter(p.tier for p in s.proposals.values() if p.table == main)
    return {
        "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        "file": s.files[main], "rows_before": len(s.originals[main]), "rows_after": len(s.current(main)),
        "n_cols": len(s.originals[main].columns), "val": val, "causes": causes, "privacy": s.privacy,
        "by_type": by_type.most_common(), "max_type": max_type,
        "by_col": sorted(((c, sum(v.values()), dict(v)) for c, v in by_col.items()), key=lambda t: -t[1]),
        "repairs": repairs, "tiers": tiers, "applied": len(applied),
        "unresolved": [{"row": (s.originals[main].at[p.row_id, id_col] if id_col else p.row_id), "column": p.column,
                        "value": p.original_value, "tier": p.tier,
                        "why": p.refusal_reason or (f"suggested '{p.candidates[0].value}' "
                                                    f"({p.candidates[0].confidence:.0%})" if p.candidates else "")}
                       for p in unresolved[:200]],
        "n_unresolved": len(unresolved), "rules": scan.rules, "bench": s.benchmark_result, "audit": audit,
        "checkpoints": s.checkpoint_states(), "dims": ["completeness", "validity", "consistency", "uniqueness",
                                                        "clean_rows"],
    }


def write_report(s, path: Path) -> Path:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template("report.html.j2").render(**_report_data(s))
    path.write_text(html, encoding="utf-8")
    return path


def privacy_report(s) -> pd.DataFrame:
    if not s.privacy:
        s.privacy_scan()
    cols = ["table", "column", "pii_type", "rows", "in_free_text", "risk", "validated_by", "sample_masked",
            "masked", "method"]
    return pd.DataFrame(s.privacy, columns=cols)


def export_bundle(s, out_dir: str | Path, zip_name: str = "datafix_output.zip") -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    files["cleaned_data.csv"] = out / "cleaned_data.csv"
    s.cleaned(s.main).to_csv(files["cleaned_data.csv"], index=False)
    for name in s.originals:
        if name != s.main:
            files[f"cleaned_{name}.csv"] = out / f"cleaned_{name}.csv"
            s.cleaned(name, with_status=False).to_csv(files[f"cleaned_{name}.csv"], index=False)
    files["cleaned_highlighted.xlsx"] = write_highlighted_xlsx(s, out / "cleaned_highlighted.xlsx")
    files["quality_report.html"] = write_report(s, out / "quality_report.html")
    files["change_log.csv"] = out / "change_log.csv"
    s.change_log().to_csv(files["change_log.csv"], index=False)
    files["privacy_report.csv"] = out / "privacy_report.csv"
    privacy_report(s).to_csv(files["privacy_report.csv"], index=False)
    files["cleaning_recipe.json"] = out / "cleaning_recipe.json"
    files["cleaning_recipe.json"].write_text(json.dumps(build_recipe(s), indent=1, ensure_ascii=False))
    zpath = out / zip_name
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name, p in files.items():
            z.write(p, f"datafix_output/{name}")
    files["zip"] = zpath
    return files
