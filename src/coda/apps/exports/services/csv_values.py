"""Value sanitizers shared by the CSV export services."""

from coda.domain.money import DecimalSeparator


def single_line(value: str) -> str:
    """Collapse multi-line cells so stray line breaks cannot corrupt the raw CSV."""
    return (
        value.replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u2028", " ")
        .replace("\u2029", " ")
        .replace("\ufeff", "")
    )


def format_money_value(
    value: str,
    key: str,
    decimal_separator: DecimalSeparator,
    money_columns: frozenset[str],
) -> str:
    """Render money columns in the requested Excel decimal separator style."""
    if decimal_separator is DecimalSeparator.German and key in money_columns:
        return value.replace(".", ",")
    return value
