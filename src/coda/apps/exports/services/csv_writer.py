"""CSV serialization shared by the CSV export services."""

from io import StringIO

import polars as pl

from coda.apps.exports.services.csv_values import format_money_value, single_line
from coda.domain.money import DecimalSeparator


def build_csv_from_rows(
    rows: list[dict[str, str]],
    csv_columns: list[str],
    money_columns: frozenset[str],
    decimal_separator: DecimalSeparator,
) -> str:
    """Format the values of *rows* and serialize them as a CSV string."""
    formatted_rows = [
        {
            key: format_money_value(single_line(value), key, decimal_separator, money_columns)
            for key, value in row.items()
        }
        for row in rows
    ]

    if not formatted_rows:
        schema = {column: pl.String for column in csv_columns}
        df = pl.DataFrame(schema=schema)
    else:
        df = pl.DataFrame(formatted_rows)

    buffer = StringIO()
    df.write_csv(buffer, separator=";")

    return buffer.getvalue()
