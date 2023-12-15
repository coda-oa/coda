"""
This module is responsible for importing currency data from an XML file and generating an enum class representing the currencies.
"""
from pathlib import Path
from typing import Callable, TypeAlias, TypeGuard
from xml.etree import ElementTree as et

import httpx

iso_currencies = "https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml"
output_file = "src/coda/money/_currency.py"

enum_header = """
from enum import Enum
from typing import NamedTuple


class CurrencyDetails(NamedTuple):
    code: str
    name: str
    minor_units: int


class Currency(Enum):
""".strip()

enum_entry = """
    {code} = CurrencyDetails(code="{code}", name="{name}", minor_units={minor_units})
""".rstrip()

enum_methods = """
    @staticmethod
    def from_code(code: str) -> "Currency":
        return getattr(Currency, code)

    @staticmethod
    def allcodes() -> set[str]:
        return {c.code for c in Currency}
    
    @property
    def code(self) -> str:
        return self.value.code

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def minor_units(self) -> int:
        return self.value.minor_units
"""


response = httpx.get(iso_currencies).raise_for_status()

root = et.fromstring(response.content)
entries = root.findall(".//CcyNtry")


def parse_tag(entry: et.Element, tag: str) -> str | None:
    return entry.findtext(tag)


def parse_entry(entry: et.Element) -> dict[str, str | int | None]:
    code = parse_tag(entry, "Ccy")
    name = parse_tag(entry, "CcyNm")
    minor_units = parse_tag(entry, "CcyMnrUnts")

    return {
        "code": code,
        "name": name,
        "minor_units": int(minor_units)
        if minor_units is not None and minor_units != "N.A."
        else None,
    }


def is_valid(entry: dict[str, str | int | None]) -> TypeGuard[dict[str, str | int]]:
    return all(v is not None for v in entry.values()) and entry["code"] != "None"


CurrencyDetails: TypeAlias = dict[str, str | int]


def duplicate_currency_filter() -> Callable[[CurrencyDetails], bool]:
    seen = set[str]()

    def no_duplicate(entry: dict[str, str | int]) -> bool:
        val = entry["code"]
        if val in seen:
            return False

        seen.add(str(val))
        return True

    return no_duplicate


def generate_enum(entries: list[et.Element]) -> str:
    parsed = map(parse_entry, entries)
    only_valid = filter(is_valid, parsed)
    only_valid = filter(duplicate_currency_filter(), only_valid)
    sorted_entries = sorted(only_valid, key=lambda e: e["code"])

    return (
        enum_header
        + "".join(enum_entry.format(**entry) for entry in sorted_entries)
        + "\n"
        + enum_methods
        + "\n"
    )


if __name__ == "__main__":
    Path(output_file).write_text(generate_enum(entries))
