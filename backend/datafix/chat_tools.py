"""Dataset chatbot (docs/06_AI_PRIVACY_SPEC.md §3).

Gemini only chooses a whitelisted tool and its arguments; the arguments are validated here and the backend runs
its own pandas code. No eval/exec/df.query on model output. Numbers in answers come from tool results.
"""
import json
import re

import pandas as pd

from . import validators as v
from .knowledge import CITY_ALIASES
from .llm import LLMUnavailable, get_llm, sanitize, thinking_config
from .privacy import mask_text, mask_value

ROW = "__row__"
PII_TYPES = {"email", "phone", "aadhaar", "pan", "gstin", "ifsc"}
OPS = ["eq", "neq", "contains", "gt", "lt", "is_missing", "has_issue"]
MAX_ROUNDS = 3


class ToolError(ValueError):
    pass


FILTERS_SCHEMA = {
    "type": "array", "description": "Row filters, all must match",
    "items": {"type": "object", "properties": {
        "column": {"type": "string"}, "op": {"type": "string", "enum": OPS},
        "value": {"type": "string", "description": "Comparison value (omit for is_missing / has_issue)"}},
        "required": ["column", "op"]},
}
TOOLS = [
    {"name": "count_rows", "description": "Count rows of the current (repaired) data matching filters.",
     "parameters": {"type": "object", "properties": {"filters": FILTERS_SCHEMA}}},
    {"name": "list_rows", "description": "Show up to 20 rows matching filters (personal data is masked).",
     "parameters": {"type": "object", "properties": {
         "filters": FILTERS_SCHEMA, "columns": {"type": "array", "items": {"type": "string"}},
         "limit": {"type": "integer"}}}},
    {"name": "group_count", "description": "Count rows per value of a column, optionally filtered.",
     "parameters": {"type": "object", "properties": {"column": {"type": "string"}, "filters": FILTERS_SCHEMA,
                                                     "top": {"type": "integer"}}, "required": ["column"]}},
    {"name": "column_stats", "description": "Type, missing count, distinct values, top values, min/median/max.",
     "parameters": {"type": "object", "properties": {"column": {"type": "string"}}, "required": ["column"]}},
    {"name": "issue_summary", "description": "Data-quality issues found, fixed and still open, optionally for one column.",
     "parameters": {"type": "object", "properties": {"column": {"type": "string"}}}},
    {"name": "explain_change", "description": "Why a row was changed or not: changes with evidence, open suggestions "
                                              "and refusals. `row` is the row number shown in the app or the record ID.",
     "parameters": {"type": "object", "properties": {"row": {"type": "string"}, "column": {"type": "string"}},
                    "required": ["row"]}},
    {"name": "least_confident_repairs", "description": "Applied repairs and pending suggestions with the lowest confidence.",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "find_duplicates", "description": "Values that occur more than once in a column, plus duplicate rows found.",
     "parameters": {"type": "object", "properties": {"column": {"type": "string"}}, "required": ["column"]}},
    {"name": "root_causes", "description": "Why the data was dirty: error sources and mechanisms.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "propose_undo", "description": "Prepare (not execute) an undo of a checkpoint or of all changes in a column. "
                                            "The user must confirm in the app.",
     "parameters": {"type": "object", "properties": {"checkpoint_id": {"type": "string"},
                                                     "column": {"type": "string"}}}},
]


class ChatTools:
    def __init__(self, session):
        self.s = session
        self.table = session.main
        self.cols = session.scans[self.table].columns
        self.last_table: dict | None = None
        self.proposed_action: dict | None = None

    # ------------------------------------------------------------ helpers
    @property
    def df(self) -> pd.DataFrame:
        return self.s.current(self.table)

    def _col(self, name: str | None) -> str:
        if not name:
            raise ToolError("column is required")
        cols = list(self.df.columns)
        for c in cols:
            if c == name or c.casefold() == str(name).casefold():
                return c
        key = v.norm_key(str(name)).replace(" ", "_")
        for c in cols:
            if v.norm_key(c).replace(" ", "_") == key:
                return c
        raise ToolError(f"unknown column {name!r}; columns are {cols}")

    def _ptype(self, col: str) -> str:
        return self.cols[col].semantic_type if col in self.cols else "unknown"

    def _show(self, col: str, x: str) -> str:
        t = self._ptype(col)
        if t in PII_TYPES:
            return mask_value(x, t, "partial")
        if t == "text":
            return mask_text(x, "partial")
        return x

    def _canon(self, x: str) -> str:
        k = v.norm_key(x)
        return v.norm_key(CITY_ALIASES.get(k, k))

    def _mask(self, filters: list | None) -> pd.Series:
        df = self.df
        m = pd.Series(True, index=df.index)
        for f in filters or []:
            if not isinstance(f, dict):
                raise ToolError("each filter must be an object")
            col, op, val = self._col(f.get("column")), f.get("op"), str(f.get("value", ""))
            if op not in OPS:
                raise ToolError(f"unknown op {op!r}")
            s = df[col]
            if op == "eq":
                target = self._canon(val)
                m &= s.map(lambda x: self._canon(x) == target)
            elif op == "neq":
                target = self._canon(val)
                m &= s.map(lambda x: self._canon(x) != target)
            elif op == "contains":
                m &= s.str.casefold().str.contains(val.casefold(), regex=False)
            elif op in ("gt", "lt"):
                try:
                    num = float(val)
                except ValueError:
                    raise ToolError(f"{op} needs a number")
                parsed = s.map(lambda x: v.parse_money(x))
                m &= parsed.map(lambda p: p is not None and (p > num if op == "gt" else p < num))
            elif op == "is_missing":
                m &= s.str.strip() == ""
            elif op == "has_issue":
                rows = {i.row_id for i in self.s.scans[self.table].issues if i.column == col and i.row_id is not None}
                m &= pd.Series(df.index.isin(list(rows)), index=df.index)
        return m

    def _row(self, ref: str) -> int:
        ref = str(ref).strip().lstrip("#")
        if ref.isdigit() and int(ref) in self.s.originals[self.table].index:
            return int(ref)
        for c, i in self.cols.items():
            if i.semantic_type == "id":
                hit = self.s.originals[self.table].index[self.s.originals[self.table][c].str.strip() == ref]
                if len(hit):
                    return int(hit[0])
        raise ToolError(f"no row {ref!r}")

    # ------------------------------------------------------------ tools
    def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"t_{name}", None)
        if fn is None or name not in {t["name"] for t in TOOLS}:
            raise ToolError(f"unknown tool {name!r}")
        return fn(**(args or {}))

    def t_count_rows(self, filters=None):
        m = self._mask(filters)
        return {"count": int(m.sum()), "of_rows": len(self.df)}

    def t_list_rows(self, filters=None, columns=None, limit=10):
        m = self._mask(filters)
        cols = [self._col(c) for c in columns] if columns else list(self.df.columns)[:8]
        sub = self.df[m].head(max(1, min(int(limit or 10), 20)))
        rows = [[str(r)] + [self._show(c, sub.at[r, c]) for c in cols] for r in sub.index]
        self.last_table = {"columns": ["row"] + cols, "rows": rows}
        return {"matching": int(m.sum()), "columns": ["row"] + cols, "rows": rows}

    def t_group_count(self, column, filters=None, top=10):
        col = self._col(column)
        s = self.df[self._mask(filters)][col].str.strip().replace("", "(blank)")
        vc = s.value_counts().head(max(1, min(int(top or 10), 20)))
        groups = [{"value": self._show(col, k), "count": int(n)} for k, n in vc.items()]
        self.last_table = {"columns": [col, "rows"], "rows": [[g["value"], str(g["count"])] for g in groups]}
        return {"column": col, "groups": groups, "distinct": int(s.nunique())}

    def t_column_stats(self, column):
        col = self._col(column)
        s = self.df[col]
        t = self._ptype(col)
        out = {"column": col, "type": t, "rows": len(s), "blank": int((s.str.strip() == "").sum()),
               "distinct": int(s.nunique())}
        if t in ("number", "money", "age"):
            nums = s.map(v.parse_money).dropna().astype(float)
            if len(nums):
                out.update(min=float(nums.min()), median=float(nums.median()), max=float(nums.max()))
        if t not in PII_TYPES and t != "text":
            out["top_values"] = {k: int(n) for k, n in s.value_counts().head(5).items()}
        return out

    def t_issue_summary(self, column=None):
        col = self._col(column) if column else None
        issues = [i for i in self.s.scans[self.table].issues if i.row_id is not None and (col is None or i.column == col)]
        by_type = {}
        for i in issues:
            by_type[i.type] = by_type.get(i.type, 0) + 1
        props = [p for p in self.s.proposals.values() if p.table == self.table and (col is None or p.column == col)]
        state = {}
        for p in props:
            k = "applied" if p.status == "applied" else f"{p.tier} (pending)" if p.status == "pending" else p.status
            state[k] = state.get(k, 0) + 1
        return {"column": col or "all", "issues_found": by_type, "repair_status": state}

    def t_explain_change(self, row, column=None):
        r = self._row(row)
        col = self._col(column) if column else None
        changes = [{"change_id": c.change_id, "column": c.column, "before": self._show(c.column, c.original_value),
                    "after": self._show(c.column, c.new_value) if c.column != ROW else "row merged/removed",
                    "status": c.status, "confidence": c.confidence, "reason": c.reason,
                    "evidence": [mask_text(e, "partial") for e in c.evidence[:4]], "source": c.source}
                   for c in self.s.changes if c.table == self.table and c.row_id == r and c.action == "apply"
                   and (col is None or c.column == col)]
        pending = [{"column": p.column, "value": self._show(p.column, p.original_value), "tier": p.tier,
                    "suggestion": (self._show(p.column, p.candidates[0].value) if p.candidates else None),
                    "confidence": p.confidence, "refusal_reason": p.refusal_reason}
                   for p in self.s.proposals.values() if p.table == self.table and p.row_id == r
                   and p.status == "pending" and (col is None or p.column == col)]
        return {"row": r, "changes": changes, "open_items": pending,
                "note": "no changes and no open items" if not changes and not pending else ""}

    def t_least_confident_repairs(self, limit=5):
        n = max(1, min(int(limit or 5), 10))
        applied = sorted((c for c in self.s.applied_changes(self.table) if c.algorithm not in ("privacy_mask", "privacy_drop")),
                         key=lambda c: c.confidence)[:n]
        pending = sorted((p for p in self.s.proposals.values() if p.table == self.table and p.status == "pending"
                          and p.tier == "review" and p.candidates), key=lambda p: p.confidence)[:n]
        return {"applied": [{"row": c.row_id, "column": c.column, "after": self._show(c.column, c.new_value),
                             "confidence": c.confidence, "reason": c.reason} for c in applied],
                "waiting_for_review": [{"row": p.row_id, "column": p.column, "suggestion": self._show(p.column, p.candidates[0].value),
                                        "confidence": p.confidence} for p in pending]}

    def t_find_duplicates(self, column):
        col = self._col(column)
        s = self.df[col].str.strip()
        s = s[s != ""]
        vc = s.value_counts()
        dup = vc[vc > 1].head(10)
        rows = [i for i in self.s.scans[self.table].issues if i.type in ("duplicate", "near_duplicate")]
        self.last_table = {"columns": [col, "rows"], "rows": [[self._show(col, k), str(n)] for k, n in dup.items()]}
        return {"column": col, "values_repeated": int((vc > 1).sum()),
                "top": [{"value": self._show(col, k), "count": int(n)} for k, n in dup.items()],
                "duplicate_rows_detected": len(rows),
                "duplicate_rows_merged": sum(1 for c in self.s.applied_changes(self.table) if c.column == ROW)}

    def t_root_causes(self):
        causes = self.s.causes if self.s.causes is not None else self.s.diagnose()
        return {"causes": [{"title": c["title"], "fix": c["suggested_fix"]} for c in causes[:8]]}

    def t_propose_undo(self, checkpoint_id=None, column=None):
        if checkpoint_id:
            k = next((k for k in self.s.checkpoints if k.checkpoint_id == str(checkpoint_id).upper()), None)
            if k is None:
                raise ToolError(f"no checkpoint {checkpoint_id!r}")
            self.proposed_action = {"kind": "undo_checkpoint", "label": f"Undo '{k.label}' ({len(k.change_ids)} changes)",
                                    "payload": {"checkpoint_id": k.checkpoint_id}}
        elif column:
            col = self._col(column)
            ids = [c.change_id for c in self.s.applied_changes(self.table) if c.column == col]
            if not ids:
                raise ToolError(f"no applied changes in {col}")
            self.proposed_action = {"kind": "undo_changes", "label": f"Undo all {len(ids)} changes in {col}",
                                    "payload": {"change_ids": ids}}
        else:
            raise ToolError("give a checkpoint_id or a column")
        return {"prepared": self.proposed_action["label"], "note": "the user must confirm this in the app"}


# ---------------------------------------------------------------- conversation

def _system_prompt(s) -> str:
    scan = s.scans[s.main]
    cols = ", ".join(f"{c} ({i.semantic_type})" for c, i in scan.columns.items())
    cps = "; ".join(f"{k.checkpoint_id} {k.label}" for k in s.checkpoints)
    return (f"You are DataFix's assistant for the table '{s.main}' ({len(s.current())} rows now). Columns: {cols}. "
            f"Checkpoints: {cps}. Always call a tool to get facts; answer ONLY from tool results, keep numbers exact, "
            "and say so if a tool cannot answer. Row numbers are the row numbers shown in the app. Answer in at most "
            "4 short sentences. Mention confidence only when a tool returned one for a repair, as a percentage "
            "(0.76 -> 76%). For undo requests call propose_undo and tell the user to confirm in the app; you cannot "
            "change data yourself. Never reveal personal data beyond the masked values tools return.")


def answer(s, message: str, history: list[dict] | None = None) -> dict:
    tools = ChatTools(s)
    calls: list[dict] = []
    llm = get_llm()
    if llm.enabled:
        try:
            text = _gemini_answer(s, tools, message, history or [], calls)
            return _reply(text, calls, tools, "gemini")
        except LLMUnavailable:
            calls.clear()
            tools = ChatTools(s)
    text = _offline_answer(tools, message, calls)
    return _reply(text, calls, tools, "offline")


def _reply(text: str, calls: list[dict], tools: ChatTools, mode: str) -> dict:
    return {"text": text, "tool_calls": calls, "table": tools.last_table, "proposed_action": tools.proposed_action,
            "mode": mode}


def _call(tools: ChatTools, name: str, args: dict, calls: list[dict]) -> dict:
    try:
        result = tools.run(name, args)
    except ToolError as e:
        result = {"error": str(e)}
    except Exception as e:  # never let a bad argument crash the chat
        result = {"error": f"{type(e).__name__}: {e}"}
    result = sanitize(result)
    preview = json.dumps(result, ensure_ascii=False, default=str)
    calls.append({"name": name, "args": args, "result_preview": json.loads(preview[:2000]) if len(preview) <= 2000
                  else {"truncated": preview[:2000]}})
    return result


def _gemini_answer(s, tools: ChatTools, message: str, history: list[dict], calls: list[dict]) -> str:
    from google.genai import types
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters=t["parameters"])
             for t in TOOLS]
    cfg = types.GenerateContentConfig(
        system_instruction=_system_prompt(s), temperature=0, thinking_config=thinking_config(),
        tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = [types.Content(role="user" if h.get("role") == "user" else "model",
                              parts=[types.Part(text=sanitize(str(h.get("text", ""))))]) for h in history[-6:]]
    contents.append(types.Content(role="user", parts=[types.Part(text=sanitize(message))]))
    llm = get_llm()
    for _ in range(MAX_ROUNDS):
        resp = llm.generate(contents, cfg)
        fcs = resp.function_calls or []
        if not fcs:
            return (resp.text or "").strip() or "I couldn't find an answer in the data."
        contents.append(resp.candidates[0].content)
        parts = []
        for fc in fcs:
            result = _call(tools, fc.name, dict(fc.args or {}), calls)
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
        contents.append(types.Content(role="user", parts=parts))
    resp = llm.generate(contents, cfg)
    return (resp.text or "").strip() or "I ran out of steps; please ask a narrower question."


# ---------------------------------------------------------------- offline intent router (no key / no internet)

def _offline_answer(tools: ChatTools, message: str, calls: list[dict]) -> str:
    msg = message.strip()
    low = msg.lower()
    m = re.search(r"why (?:did|was|has) (?:row|record)\s*#?\s*([\w-]+)", low)
    if m:
        r = _call(tools, "explain_change", {"row": m.group(1)}, calls)
        if "error" in r:
            return r["error"]
        parts = [f"row {r['row']}: {c['column']} '{c['before']}' → '{c['after']}' ({c['confidence']:.0%}, {c['status']}) "
                 f"because {c['evidence'][0] if c['evidence'] else c['reason']}" for c in r["changes"]]
        parts += [f"{p['column']} is still open ({p['tier']}): {p['refusal_reason'] or 'suggested ' + str(p['suggestion'])}"
                  for p in r["open_items"]]
        return "; ".join(parts) or f"Row {r['row']} has no changes and no open items."
    m = re.search(r"how many .*?(?:from|in|at) ([a-z .]+?)\??$", low)
    if m:
        place = m.group(1).strip()
        for col in [c for c, i in tools.cols.items() if i.semantic_type in ("city", "state", "district")]:
            r = _call(tools, "count_rows", {"filters": [{"column": col, "op": "eq", "value": place}]}, calls)
            if r.get("count"):
                return f"{r['count']:,} of {r['of_rows']:,} rows have {col} = {place.title()}."
        return f"No rows match '{place}'."
    if re.search(r"least (?:sure|confident)|lowest confidence|not sure", low):
        r = _call(tools, "least_confident_repairs", {"limit": 5}, calls)
        a = ", ".join(f"row {x['row']} {x['column']} ({x['confidence']:.0%})" for x in r["applied"][:3])
        w = ", ".join(f"row {x['row']} {x['column']} ({x['confidence']:.0%})" for x in r["waiting_for_review"][:3])
        return f"Least confident applied repairs: {a or 'none'}. Waiting for review: {w or 'none'}."
    m = re.search(r"duplicates? (?:in|of) (?:the )?([\w ]+?)(?: column)?\??$", low)
    if m:
        r = _call(tools, "find_duplicates", {"column": m.group(1).strip()}, calls)
        if "error" in r:
            return r["error"]
        return (f"{r['values_repeated']} {r['column']} values occur more than once; {r['duplicate_rows_detected']} "
                f"duplicate rows were detected and {r['duplicate_rows_merged']} merged.")
    m = re.search(r"undo (?:the |all )?([\w ]+?) (?:fix|fixes|changes|repairs)", low)
    if m:
        r = _call(tools, "propose_undo", {"column": m.group(1).strip()}, calls)
        return r.get("error") or f"Prepared: {r['prepared']}. Confirm it in the app to apply."
    if re.search(r"why .*(dirty|errors?|wrong)|root cause", low):
        r = _call(tools, "root_causes", {}, calls)
        return " ".join(c["title"] + "." for c in r["causes"][:3])
    m = re.search(r"(?:issues|problems|errors) (?:in|with) (?:the )?(\w+)", low)
    r = _call(tools, "issue_summary", {"column": m.group(1)} if m else {}, calls)
    if "error" in r:
        r = _call(tools, "issue_summary", {}, calls)
    found = ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in r["issues_found"].items())
    status = ", ".join(f"{k} {n}" for k, n in r["repair_status"].items())
    return f"Issues found ({r['column']}): {found}. Repair status: {status}. " \
           "(Offline mode: I understand questions about counts, rows, duplicates, confidence, causes and undo.)"
