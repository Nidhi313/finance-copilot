from decimal import Decimal as D

import pytest

from app.countries.pack_schema import CsvMapping
from app.services.csv_import import CsvFormatError, parse_csv

COMMBANK = CsvMapping(has_header=False, date_column=0, date_format="%d/%m/%Y", description_columns=[2], amount_column=1)
HDFC = CsvMapping(
    has_header=True,
    date_column="Date",
    date_format="%d/%m/%y",
    description_columns=["Narration"],
    debit_column="Withdrawal Amt.",
    credit_column="Deposit Amt.",
)


def test_headerless_signed_amounts():
    text = (
        '28/10/2026,"-85.40","WOOLWORTHS 1234 SYDNEY","+1,914.60"\n'
        '27/10/2026,"+2,000.00","SALARY ACME PTY LTD","+2,000.00"\n'
    )
    r = parse_csv(text, COMMBANK)
    assert [row.amount for row in r.rows] == [D("-85.40"), D("2000.00")]
    assert r.rows[0].description == "WOOLWORTHS 1234 SYDNEY"
    assert r.errors == []


def test_finds_header_below_bank_preamble_and_reports_bad_rows():
    text = (
        "HDFC BANK Ltd.\n"
        "Account No : XXXX1234\n"
        "\n"
        " Date     ,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "01/10/26,SWIGGY ORDER,0001,01/10/26,450.00,,10550.00\n"
        '02/10/26,NEFT SALARY,0002,02/10/26,,"85,000.00",95550.00\n'
        "Statement Summary,,,,,,\n"
    )
    r = parse_csv(text, HDFC)
    assert r.header[0] == "Date"
    assert [row.amount for row in r.rows] == [D("-450.00"), D("85000.00")]
    assert len(r.errors) == 1 and r.errors[0]["line"] == 7


def test_identical_rows_in_one_file_are_both_kept():
    text = "01/10/2026,-4.50,COFFEE\n01/10/2026,-4.50,COFFEE\n"
    m = CsvMapping(has_header=False, date_column=0, description_columns=[2], amount_column=1)
    r = parse_csv(text, m)
    assert len(r.rows) == 2
    assert r.rows[0].dedupe_hash != r.rows[1].dedupe_hash


def test_same_file_gives_same_hashes():
    text = "01/10/2026,-4.50,COFFEE\n02/10/2026,-9.00,LUNCH\n"
    m = CsvMapping(has_header=False, date_column=0, description_columns=[2], amount_column=1)
    a, b = parse_csv(text, m), parse_csv(text, m)
    assert [r.dedupe_hash for r in a.rows] == [r.dedupe_hash for r in b.rows]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(12.30)", D("-12.30")),
        ("$1,234.50", D("1234.50")),
        ("₹2,500", D("2500.00")),
        ("100.00 DR", D("-100.00")),
        ("100.00CR", D("100.00")),
        ("A$5", D("5.00")),
    ],
)
def test_amount_formats(raw, expected):
    m = CsvMapping(has_header=False, date_column=0, description_columns=[2], amount_column=1)
    r = parse_csv(f'01/10/2026,"{raw}",X\n', m)
    assert r.rows[0].amount == expected


def test_invert_amounts_for_credit_cards():
    m = CsvMapping(has_header=False, date_column=0, description_columns=[2], amount_column=1, invert_amounts=True)
    assert parse_csv("01/10/2026,50.00,SHOP\n", m).rows[0].amount == D("-50.00")


def test_comma_decimal_separator():
    m = CsvMapping(
        has_header=False, delimiter=";", date_column=0, description_columns=[2], amount_column=1, decimal_separator=","
    )
    assert parse_csv("01/10/2026;-1.234,56;SHOP\n", m).rows[0].amount == D("-1234.56")


def test_missing_header_column_is_a_clear_error():
    with pytest.raises(CsvFormatError, match="Date"):
        parse_csv("a,b,c\n1,2,3\n", HDFC)


def test_mapping_rejects_names_without_header():
    with pytest.raises(ValueError):
        CsvMapping(has_header=False, date_column="Date", description_columns=[1], amount_column=2)
