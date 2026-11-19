"""Value families, canonical formats, state codes, job synonyms and age-from-DOB (synthetic tables)."""
import random
from datetime import date

import pandas as pd

from datafix.detect.crossfield import age_on
from datafix.planner import plan_repairs
from datafix.repair.age import words_to_age
from datafix.scan import scan_table


def _plan(df: pd.DataFrame) -> dict[tuple[int, str], tuple[str, str]]:
    df = df.astype(str)
    scans = {"t": scan_table(df, "t")}
    return {(p.row_id, p.column): (p.tier, p.candidates[0].value if p.candidates else "")
            for p in plan_repairs({"t": df}, scans)}


def _people(n=400, seed=1):
    rng = random.Random(seed)
    first = ["Rahul", "Priya", "Amit", "Sneha", "Kiran", "Meera", "Ravi", "Anita"]
    last = ["Sharma", "Iyer", "Rao", "Nair", "Das", "Gupta", "Shetty", "Menon"]
    rows = []
    for i in range(n):
        dob = date(rng.randint(1950, 2004), rng.randint(1, 12), rng.randint(1, 28))
        name = f"{rng.choice(first)} {rng.choice(last)}"
        rows.append({"id": f"C{i:04d}", "name": name, "gender": rng.choice(["Male", "Female"]),
                     "is_active": rng.choice(["true", "false"]), "dob": dob.isoformat(),
                     "age": str(age_on(dob, date(2026, 11, 19))),
                     "email": f"{name.lower().replace(' ', '.')}{i}@gmail.com",
                     "phone": f"9{rng.randint(100000000, 999999999)}", "pan": f"ABCP{chr(65 + i % 26)}{1000 + i}K",
                     "state": rng.choice(["Karnataka", "Maharashtra", "Uttar Pradesh"]),
                     "occupation": rng.choice(["Homemaker", "Doctor", "Banker", "Teacher"])})
    return pd.DataFrame(rows)


def test_family_synonyms_map_to_column_style():
    df = _people()
    for r, (g, b) in enumerate([("m", "YES"), ("F", "y"), ("female", "1"), ("MALE", "Inactive"), ("M", "n")]):
        df.at[r, "gender"], df.at[r, "is_active"] = g, b
    plan = _plan(df)
    assert [plan[(r, "gender")][1] for r in range(5)] == ["Male", "Female", "Female", "Male", "Male"]
    assert [plan[(r, "is_active")][1] for r in range(5)] == ["true", "true", "true", "false", "false"]
    assert all(plan[(r, "gender")][0] == "auto" for r in range(5))


def test_family_needs_mixed_styles_and_coverage():
    df = _people()
    df["flag"] = ["Y" if i % 2 else "N" for i in range(len(df))]  # one consistent style: not an error
    plan = _plan(df)
    assert not any(c == "flag" for _, c in plan)


def test_canonical_formats_only_when_dominant():
    df = _people()
    df.at[0, "phone"] = "+91 98450 12345"
    df.at[1, "phone"] = "(984) 501 2345"
    df.at[2, "email"] = " Rahul.Sharma2@GMAIL.COM "
    df.at[3, "pan"] = "abcpd1003k"
    df.at[4, "name"] = "sNEHA d'sOUZA"
    plan = _plan(df)
    assert plan[(0, "phone")] == ("auto", "9845012345") and plan[(1, "phone")] == ("auto", "9845012345")
    assert plan[(2, "email")] == ("auto", "rahul.sharma2@gmail.com")
    assert plan[(3, "pan")] == ("auto", "ABCPD1003K")
    assert plan[(4, "name")] == ("auto", "Sneha D'Souza")
    # a column that is consistently '+91 ...' is a style choice, not an error
    df2 = _people()
    df2["phone"] = [f"+91 {p[:5]} {p[5:]}" for p in df2["phone"]]
    assert not any(c == "phone" for _, c in _plan(df2))


def test_mixed_case_names_are_left_alone():
    df = _people()
    df.at[0, "name"] = "Ravi McDonald"
    assert (0, "name") not in _plan(df)


def test_state_codes_and_job_synonyms():
    df = _people()
    df.at[0, "state"], df.at[1, "state"], df.at[2, "occupation"] = "U.P.", "KA", "Housewife"
    plan = _plan(df)
    assert plan[(0, "state")][1] == "Uttar Pradesh" and plan[(1, "state")][1] == "Karnataka"
    assert plan[(2, "occupation")][1] == "Homemaker"


def test_age_from_dob_when_rule_holds():
    df = _people()
    df.at[0, "age"] = ""
    df.at[1, "age"] = "999"
    df.at[2, "age"], df.at[2, "dob"] = "thirty", "1996-01-01"  # 30 on 2026-11-19: words agree with dob
    df.at[5, "age"], df.at[5, "dob"] = "forty", "1996-01-01"   # words disagree with dob: not auto
    expected = [age_on(date.fromisoformat(df.at[r, "dob"]), date(2026, 11, 19)) for r in range(3)]
    df.at[3, "age"] = str(expected[0])[::-1] if str(expected[0])[::-1] != str(expected[0]) else "1"
    plan = _plan(df)
    assert [plan[(r, "age")] for r in range(3)] == [("auto", str(e)) for e in expected]
    assert plan[(3, "age")][1] == str(age_on(date.fromisoformat(df.at[3, "dob"]), date(2026, 11, 19)))
    assert plan[(5, "age")][0] != "auto"


def test_age_rule_not_learned_from_random_ages():
    df = _people()
    rng = random.Random(3)
    df["age"] = [str(rng.randint(18, 80)) for _ in range(len(df))]
    df.at[0, "age"] = ""
    tier, value = _plan(df).get((0, "age"), ("refused", ""))
    assert tier != "auto"  # no proven rule: never auto-filled


def test_words_to_age():
    assert [words_to_age(x) for x in ("thirty", "Forty-two", "fifty five", "abc", "")] == [30, 42, 55, None, None]
