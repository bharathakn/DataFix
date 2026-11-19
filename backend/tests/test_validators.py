import pytest

from datafix import validators as v


def test_verhoeff_and_aadhaar():
    assert v.verhoeff_ok("2363")  # textbook example: 236 + check digit 3
    assert not v.verhoeff_ok("2364")
    assert v.is_aadhaar("2345 6789 0124") is v.verhoeff_ok("234567890124")
    assert not v.is_aadhaar("1234 5678 9012")  # Aadhaar never starts with 0/1


def test_luhn_card():
    assert v.is_card("4111 1111 1111 1111")
    assert not v.is_card("4111 1111 1111 1112")


def test_gstin_checksum():
    assert v.is_gstin("27AAPFU0939F1ZV")
    assert not v.is_gstin("27AAPFU0939F1ZX")


def test_pan_ifsc():
    assert v.is_pan("ABCPK1234Z")
    assert not v.is_pan("ABCXK1234Z")  # 4th char must be an entity type
    assert v.is_ifsc("SBIN0001234")


@pytest.mark.parametrize("raw,ok", [
    ("9876543210", True), ("+91 98765-43210", True), ("09876543210", True), ("919876543210", True),
    ("98765", False), ("1234567890", False), ("9.87654E+09", False),
])
def test_phone(raw, ok):
    assert v.is_phone(raw) is ok


@pytest.mark.parametrize("raw,ok", [
    ("rahul@gmail.com", True), ("arjun@gmail", False), ("a@@gmail.com", False), ("a @gmail.com", False),
    ("rahulgmail.com", False),
])
def test_email(raw, ok):
    assert v.is_email(raw) is ok


@pytest.mark.parametrize("raw,value,style", [
    ("₹1.2L", 120000, "lakh"), ("12,00,000", 1200000, "commas"), ("1.5 Cr", 15000000, "crore"),
    ("Rs. 5000", 5000, "symbol"), ("340000", 340000, "plain"), ("2.5k", 2500, "short"),
])
def test_money(raw, value, style):
    assert v.parse_money(raw) == pytest.approx(value)
    assert v.money_style(raw) == style


def test_dates():
    assert v.date_families("23/05/2024") == {"dmy"}
    assert v.date_families("05/23/2024") == {"mdy"}
    assert v.date_families("03/04/2024") == {"dmy", "mdy"}
    assert v.date_families("2023-02-12T17:17:00") == {"iso"}
    assert v.date_families("31/02/2024") == frozenset()


def test_misc():
    assert v.is_age("41") and not v.is_age("-5") and not v.is_age("150") and not v.is_age("0")
    assert v.has_mojibake("Dâ€™Souza") and not v.has_mojibake("D’Souza")
    assert v.has_mojibake("D’Souza".encode().decode("latin-1"))
    assert v.norm_key("  Pune. ") == "pune"
    assert v.is_sci_notation("9.87654E+09")
