import re
from typing import Any, NamedTuple, Protocol

from coda.string import NonEmptyStr

from pydantic_core import PydanticCustomError
from pydantic_extra_types.isbn import ISBN


class Link(Protocol):
    @property
    def type(self) -> str:
        ...

    @property
    def url(self) -> str:
        ...


class UserLink(NamedTuple):
    type: str
    value: str
    url_prefix: str = ""

    @property
    def url(self) -> str:
        return self.url_prefix + self.value

    def __str__(self) -> str:
        return self.value


class Isbn:
    __slot__ = ("_value",)
    __match_args__ = ("_value",)

    def __init__(self, isbn: str) -> None:
        try:
            raw_isbn = NonEmptyStr(isbn.replace("-", ""))
            ISBN.validate_isbn_format(raw_isbn)
            self._value = raw_isbn
        except PydanticCustomError:
            raise ValueError(f"{isbn} is not a valid ISBN")

    @property
    def type(self) -> str:
        return "ISBN"

    @property
    def url(self) -> str:
        return f"https://isbnsearch.org/isbn/{self}"

    def is_isbn_10(self) -> bool:
        return len(self) == 10

    def is_isbn_13(self) -> bool:
        return len(self) == 13

    def to_isbn_13(self) -> "Isbn":
        if self.is_isbn_13():
            return self

        return Isbn(ISBN.convert_isbn10_to_isbn13(self._value))

    def __str__(self) -> str:
        return self._value

    def __len__(self) -> int:
        return len(self._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Isbn):
            return False

        return self._value == other._value

    def __hash__(self) -> int:
        return hash((self._value,))


class Doi:
    __match_args__ = ("_doi",)

    def __init__(self, doi: str) -> None:
        self._doi = NonEmptyStr(doi).strip()
        if not self._valid():
            raise ValueError("Invalid DOI format")

    @property
    def type(self) -> str:
        return "DOI"

    def _valid(self) -> bool:
        """
        These regex patterns are from the Crossref documentation:
        https://www.crossref.org/blog/dois-and-matching-regular-expressions/
        """
        return any(
            (
                re.match(r"^10.\d{4,9}/[-._;()/:A-Z0-9]+$", self._doi, re.IGNORECASE),
                re.match(
                    r"^10.\d{4}/\d+-\d+X?(\d+)\d+<[\d\w]+:[\d\w]*>\d+.\d+.\w+;\d$",
                    self._doi,
                    re.IGNORECASE,
                ),
                re.match(r"^10.1021/\w\w\d++$", self._doi, re.IGNORECASE),
                re.match(r"^10.1207/[\w\d]+\&\d+_\d+$", self._doi, re.IGNORECASE),
            )
        )

    @property
    def prefix(self) -> str:
        return self._doi.split("/")[0]

    @property
    def suffix(self) -> str:
        return self._doi.split("/")[1]

    @property
    def url(self) -> str:
        return f"https://doi.org/{str(self)}"

    def __str__(self) -> str:
        return self._doi

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Doi):
            return False
        return self._doi == other._doi

    def __hash__(self) -> int:
        return hash((self._doi,))


def create_link(link_type: str, link_value: str) -> Link:
    if link_type == "DOI":
        return Doi(link_value)
    if link_type == "ISBN":
        return Isbn(link_value)

    return UserLink(type=link_type, value=link_value)
