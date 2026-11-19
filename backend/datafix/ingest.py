"""Load CSV / Excel / JSON as all-string DataFrames without altering any value."""
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from charset_normalizer import from_bytes


@dataclass
class LoadedTable:
    df: pd.DataFrame
    filename: str
    sha256: str
    encoding: str | None = None
    delimiter: str | None = None


def load_path(path: str | Path, sheet: int | str = 0) -> LoadedTable:
    p = Path(path)
    return load_bytes(p.read_bytes(), p.name, sheet)


def load_bytes(data: bytes, filename: str, sheet: int | str = 0) -> LoadedTable:
    ext = Path(filename).suffix.lower()
    sha = hashlib.sha256(data).hexdigest()
    enc = delim = None
    if ext in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(io.BytesIO(data), sheet_name=sheet, dtype=str, keep_default_na=False, na_filter=False)
    elif ext == ".json":
        text, enc = _decode(data)
        obj = json.loads(text)
        if isinstance(obj, dict):
            obj = next((v for v in obj.values() if isinstance(v, list)), [obj])
        df = pd.json_normalize(obj)
        df = df.map(lambda v: "" if v is None or (isinstance(v, float) and v != v) else str(v))
    else:
        text, enc = _decode(data)
        delim = _sniff(text)
        df = pd.read_csv(io.StringIO(text), sep=delim, dtype=str, keep_default_na=False, na_filter=False)
    return LoadedTable(_finalise(df), filename, sha, enc, delim)


def _decode(data: bytes) -> tuple[str, str]:
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        best = from_bytes(data[:2_000_000]).best()
        enc = best.encoding if best else "latin-1"
        return data.decode(enc, errors="replace"), enc


def _sniff(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _finalise(df: pd.DataFrame) -> pd.DataFrame:
    names, seen = [], {}
    for i, c in enumerate(df.columns):
        name = str(c).strip()
        if not name or name.startswith("Unnamed:"):
            name = f"col_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        names.append(name)
    df.columns = names
    return df.fillna("").astype(str).reset_index(drop=True)
