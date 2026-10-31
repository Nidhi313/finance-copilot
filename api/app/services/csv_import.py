"""Read a bank CSV into transactions, using either a country pack preset or a
user's own column mapping. Parsing is pure (no database) so it is easy to test.

Re-importing the same file never creates duplicates: each row gets a hash of
date, amount, description and how many identical rows came before it in the
file, so two genuine $4.50 coffees on the same day are kept as two rows."""

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.countries.pack_schema import CsvMapping

MAX_ERRORS_REPORTED = 50


@dataclass
class ParsedRow:
    line: int
    date: date
    description: str
    amount: Decimal
    dedupe_hash: str


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    header: list[str] | None = None
    total_lines: int = 0


class CsvFormatError(ValueError):
    pass


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise CsvFormatError("Could not read the file as text")


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _parse_amount(raw: str, decimal_separator: str) -> Decimal | None:
    s = raw.strip().replace(" ", "")
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    for symbol in ("A$", "AUD", "INR", "Rs.", "Rs", "$", "₹", "€", "£"):
        s = s.replace(symbol, "")
    if s.endswith("CR"):
        s = s[:-2]
    elif s.endswith("DR"):
        s, negative = s[:-2], True
    if decimal_separator == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        value = Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"not a number: {raw!r}") from e
    return -value if negative else value


def _find_header(rows: list[list[str]], mapping: CsvMapping) -> int:
    """Banks often put account details above the header row. Find the first row
    that contains the configured date column name."""
    target = _norm(str(mapping.date_column))
    for i, row in enumerate(rows[:50]):
        if target in {_norm(c) for c in row}:
            return i
    raise CsvFormatError(f"Could not find a header row with a column named {mapping.date_column!r}")


def parse_csv(text: str, mapping: CsvMapping) -> ParseResult:
    rows = list(csv.reader(io.StringIO(text), delimiter=mapping.delimiter))
    result = ParseResult()
    start = 0
    index: dict[str, int] = {}
    if mapping.has_header:
        h = _find_header(rows, mapping)
        result.header = [c.strip() for c in rows[h]]
        index = {_norm(c): i for i, c in enumerate(rows[h])}
        start = h + 1

    def col(ref) -> int:
        if isinstance(ref, int):
            return ref
        key = _norm(ref)
        if key not in index:
            raise CsvFormatError(f"Column {ref!r} is not in the header row")
        return index[key]

    date_i = col(mapping.date_column)
    desc_i = [col(c) for c in mapping.description_columns]
    amount_i = col(mapping.amount_column) if mapping.amount_column is not None else None
    debit_i = col(mapping.debit_column) if mapping.debit_column is not None else None
    credit_i = col(mapping.credit_column) if mapping.credit_column is not None else None
    needed = max(i for i in [date_i, *desc_i, amount_i, debit_i, credit_i] if i is not None)

    seen: dict[tuple, int] = {}
    for n, row in enumerate(rows[start:], start=start + 1):
        if not any(c.strip() for c in row):
            continue
        result.total_lines += 1
        try:
            if len(row) <= needed:
                raise ValueError(f"expected at least {needed + 1} columns, found {len(row)}")
            raw_date = row[date_i].strip()
            try:
                d = datetime.strptime(raw_date, mapping.date_format).date()
            except ValueError as e:
                raise ValueError(f"date {raw_date!r} does not match {mapping.date_format}") from e
            description = " ".join(row[i].strip() for i in desc_i if row[i].strip())
            if amount_i is not None:
                amount = _parse_amount(row[amount_i], mapping.decimal_separator)
                if amount is None:
                    raise ValueError("amount is empty")
            else:
                debit = _parse_amount(row[debit_i], mapping.decimal_separator) if debit_i is not None else None
                credit = _parse_amount(row[credit_i], mapping.decimal_separator) if credit_i is not None else None
                if debit is None and credit is None:
                    raise ValueError("both debit and credit are empty")
                amount = (credit or Decimal(0)) - abs(debit or Decimal(0))
            if mapping.invert_amounts:
                amount = -amount
        except (ValueError, IndexError) as e:
            if len(result.errors) < MAX_ERRORS_REPORTED:
                result.errors.append({"line": n, "error": str(e)})
            continue
        amount = amount.quantize(Decimal("0.01"))
        key = (d.isoformat(), str(amount), _norm(description))
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        digest = hashlib.sha256("|".join([*key, str(occurrence)]).encode()).hexdigest()
        result.rows.append(ParsedRow(n, d, description[:500] or "(no description)", amount, digest))
    return result
