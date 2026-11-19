"""Shared state for repairers: the table, its scan, linked tables and evidence helpers."""
from dataclasses import dataclass, field

import pandas as pd

from .. import validators as v
from ..confidence import signal
from ..models import Issue, Signal
from ..reference import PinReference
from ..scan import ScanResult

ERROR_TYPES = {"missing", "disguised_missing", "invalid_format", "inconsistent", "fd_violation", "crossfield"}


@dataclass
class Linked:
    name: str
    df: pd.DataFrame
    scan: ScanResult
    joins: list[tuple[str, str]]  # (main column, linked column)
    index: dict[str, dict[str, list[int]]] = field(default_factory=dict)  # linked col -> value -> rows


@dataclass
class RepairContext:
    table: str
    df: pd.DataFrame
    scan: ScanResult
    ref: PinReference | None
    linked: list[Linked] = field(default_factory=list)
    cells: dict[tuple[int, str], list[Issue]] = field(default_factory=dict)
    cache: dict = field(default_factory=dict)

    def __post_init__(self):
        for i in self.scan.issues:
            if i.row_id is not None and i.column:
                self.cells.setdefault((i.row_id, i.column), []).append(i)

    def col_type(self, col: str) -> str:
        return self.scan.columns[col].semantic_type

    def cols_of_type(self, *types: str) -> list[str]:
        return [c for c, i in self.scan.columns.items() if i.semantic_type in types]

    def is_error(self, row: int, col: str) -> bool:
        return any(i.type in ERROR_TYPES for i in self.cells.get((row, col), []))

    def value(self, row: int, col: str) -> str:
        return self.df.at[row, col]

    def trusted(self, row: int, col: str) -> str | None:
        """The cell's value if it can be used as evidence, else None."""
        if col not in self.df.columns or self.is_error(row, col):
            return None
        x = self.df.at[row, col].strip()
        return x or None

    def join_value(self, row: int, col: str) -> str | None:
        """Like trusted(), but a cell whose only problem is its written form ('A.B@GMAIL.COM') still
        joins on its canonical form."""
        x = self.trusted(row, col)
        if x is not None:
            return x
        issues = self.cells.get((row, col), [])
        canon = [i.meta["suggestion"] for i in issues if i.meta.get("kind") in ("canonical", "whitespace")]
        if canon and all(i.type == "inconsistent" for i in issues):
            return canon[0].strip() or None
        return None

    def key(self, col: str, raw: str) -> str:
        canon = self.scan.canonical.get(col, {})
        return v.norm_key(canon.get(raw, raw))

    # ---------------------------------------------------------------- learned rules as evidence
    def fd_votes(self, row: int, target: str) -> dict[str, list[Signal]]:
        """Each learned rule X->target votes for the majority value of the row's X group."""
        votes: dict[str, list[Signal]] = {}
        for m in self.scan.fd_maps.values():
            if m["rhs"] != target:
                continue
            x = m["lhs"]
            raw = self.trusted(row, x)
            if raw is None:
                continue
            g = m["groups"].get(self.key(x, raw))
            if not g or g["share"] < 0.8:
                continue
            votes.setdefault(g["value"], []).append(signal(
                "fd_majority", m["confidence"] * g["share"],
                f"learned rule {x} → {target}: {x} '{raw}' has {target} '{g['value']}' in "
                f"{g['share']:.0%} of {g['size']} rows"))
        return votes

    # ---------------------------------------------------------------- linked tables as evidence
    def linked_values(self, row: int, target_type: str) -> list[tuple[str, dict[str, int], str]]:
        """For each linked table/join that matches this row: (table, {normalised value: count}, how matched)."""
        out = []
        for lk in self.linked:
            tcols = [c for c, i in lk.scan.columns.items() if i.semantic_type == target_type]
            if not tcols:
                continue
            for main_col, link_col in lk.joins:
                key = self.join_value(row, main_col)
                if key is None:
                    continue
                if link_col not in lk.index:
                    lk.index[link_col] = _build_index(lk.df[link_col], self.col_type(main_col))
                idx = lk.index[link_col]
                rows = idx.get(_join_norm(key, self.col_type(main_col)), [])
                if not rows:
                    continue
                counts: dict[str, int] = {}
                for r in rows:
                    for tc in tcols:
                        raw = lk.df.at[r, tc]
                        norm = _clean_contact(raw, target_type)
                        if norm:
                            counts[norm] = counts.get(norm, 0) + 1
                out.append((lk.name, counts, f"{main_col} '{key}'"))
                break  # first usable join is enough
        return out


def _join_norm(x: str, col_type: str) -> str:
    x = x.strip()
    return x.casefold() if col_type == "email" else x


def _build_index(s: pd.Series, col_type: str) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    for r, x in s.items():
        if x.strip():
            idx.setdefault(_join_norm(x, col_type), []).append(r)
    return idx


def _clean_contact(raw: str, target_type: str) -> str | None:
    if target_type == "phone":
        n = v.normalize_phone(raw)
        return n if v.PHONE_RE.match(n) and not len(set(n)) == 1 else None
    if target_type == "email":
        e = raw.strip().casefold()
        return e if v.is_email(e) else None
    return raw.strip() or None


def find_joins(main: ScanResult, other: ScanResult) -> list[tuple[str, str]]:
    """Same-named ID columns first, then shared email columns."""
    joins = []
    for c, i in main.columns.items():
        if i.semantic_type == "id" and c in other.columns and other.columns[c].semantic_type == "id":
            joins.append((c, c))
    for c, i in main.columns.items():
        if i.semantic_type == "email":
            for oc, oi in other.columns.items():
                if oi.semantic_type == "email":
                    joins.append((c, oc))
    return joins
