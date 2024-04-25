from typing import NamedTuple

import pytest

from coda.author import AuthorList

csv_name_list_no_spaces = "John Doe,Jane Doe,Alice Doe"
csv_name_list_with_spaces = "John Doe, Jane Doe, Alice Doe"
csv_name_list_last_author_sep_with_comma_and = "John Doe, Jane Doe, and Alice Doe"
csv_name_list_last_author_sep_with_only_and = "John Doe, Jane Doe and Alice Doe"
semicolon_sep_name_list = "John Doe; Jane Doe; Alice Doe"
semicolon_sep_reversed_name_list = "Doe, John; Doe, Jane; Doe, Alice"
newline_sep_name_list = """
    John Doe
    Jane Doe
    Alice Doe
"""

csv_name_list_with_line_breaks = """
    John Doe,
    Jane Doe,
    Alice Doe
"""
csv_name_list_missing_space_in_name = "John Doe, Jane Doe, AliceDoe"
csv_name_list_last_author_sep_with_and_on_newline = "John Doe, Jane Doe,\nand Alice Doe"
csv_name_list_last_author_sep_with_and_before_newline = "John Doe, Jane Doe, and\nAlice Doe"


class DataPair(NamedTuple):
    actual: str
    expected: list[str]


real_world_examples = [
    DataPair(
        """Alexander H. Miller, Will Feng, Adam Fisch, Jiasen Lu,
Dhruv Batra, Antoine Bordes, Devi Parikh and Jason Weston""",
        [
            "Alexander H. Miller",
            "Will Feng",
            "Adam Fisch",
            "Jiasen Lu",
            "Dhruv Batra",
            "Antoine Bordes",
            "Devi Parikh",
            "Jason Weston",
        ],
    ),
    DataPair(
        "Hafedh Mili, Fatma Mili, and Ali Mili",
        ["Hafedh Mili", "Fatma Mili", "Ali Mili"],
    ),
    DataPair(
        """Jorge J. Moré
Stephen J. Wright""",
        ["Jorge J. Moré", "Stephen J. Wright"],
    ),
    DataPair(
        """Christopher Blech, Nils Dreyer, Bj ̈orn Friebel, Christoph R. Jacob, Mostafa Shamil Jassim, Leander Jehl, R ̈udigerKapitza, Manfred Krafczyk, Thomas K ̈urner, Sabine C. Langer, Jan Linxweiler∗, Mohammad Mahhouk, SvenMarcus, Ines Messadi, S ̈oren Peters, Jan-Marc Pilawa, Harikrishnan K. Sreekumar, Robert Str ̈otgen, Katrin Stump,Arne Vogel, Mario Wolter""",
        [
            "Christopher Blech",
            "Nils Dreyer",
            "Björn Friebel",
            "Christoph R. Jacob",
            "Mostafa Shamil Jassim",
            "Leander Jehl",
            "Rüdiger Kapitza",
            "Manfred Krafczyk",
            "Thomas Kürner",
            "Sabine C. Langer",
            "Jan Linxweiler∗",
            "Mohammad Mahhouk",
            "Sven Marcus",
            "Ines Messadi",
            "Sören Peters",
            "Jan-Marc Pilawa",
            "Harikrishnan K. Sreekumar",
            "Robert Strötgen",
            "Katrin Stump",
            "Arne Vogel",
            "Mario Wolter",
        ],
    ),
]


@pytest.mark.parametrize(
    "authors",
    [
        csv_name_list_no_spaces,
        csv_name_list_with_spaces,
        csv_name_list_last_author_sep_with_comma_and,
        csv_name_list_last_author_sep_with_only_and,
        semicolon_sep_name_list,
        semicolon_sep_reversed_name_list,
        newline_sep_name_list,
        csv_name_list_missing_space_in_name,
        csv_name_list_last_author_sep_with_and_on_newline,
        csv_name_list_last_author_sep_with_and_before_newline,
    ],
)
def test__author_list__from_str__creates_author_list_param(authors: str) -> None:
    sut = AuthorList.from_str(authors)
    assert list(sut) == ["John Doe", "Jane Doe", "Alice Doe"]


@pytest.mark.parametrize("data_pair", real_world_examples)
def test__author_list__from_str__creates_author_list_param_real_world(data_pair: DataPair) -> None:
    sut = AuthorList.from_str(data_pair.actual)
    assert list(sut) == data_pair.expected
