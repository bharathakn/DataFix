import json

import pandas as pd

from datafix.ingest import load_bytes


def test_csv_keeps_values_as_text():
    data = "id,pin,phone,note\n1,040001,9876543210,NA\n2,,1.2E+09, x \n".encode()
    df = load_bytes(data, "t.csv").df
    assert df.loc[0, "pin"] == "040001"  # leading zero kept
    assert df.loc[0, "note"] == "NA"  # not converted to NaN
    assert df.loc[1, "pin"] == ""
    assert df.loc[1, "note"] == " x "  # whitespace kept for detection


def test_semicolon_and_latin1():
    data = "name;city\nJosé;Pune\n".encode("latin-1")
    lt = load_bytes(data, "t.csv")
    assert lt.delimiter == ";" and lt.df.loc[0, "name"] == "José"


def test_excel_and_json(tmp_path):
    path = tmp_path / "t.xlsx"
    pd.DataFrame({"a": ["x", None], "b": [1, 2]}).to_excel(path, index=False)
    df = load_bytes(path.read_bytes(), "t.xlsx").df
    assert df["a"].tolist() == ["x", ""] and df["b"].tolist() == ["1", "2"]

    js = json.dumps({"data": [{"a": 1, "b": {"c": None}}, {"a": 2, "b": {"c": "y"}}]}).encode()
    df = load_bytes(js, "t.json").df
    assert df["a"].tolist() == ["1", "2"] and df["b.c"].tolist() == ["", "y"]


def test_blank_and_duplicate_headers():
    df = load_bytes(b"a,,a\n1,2,3\n", "t.csv").df
    assert list(df.columns) == ["a", "col_2", "a.1"]  # pandas de-duplicates CSV headers as "a.1"
