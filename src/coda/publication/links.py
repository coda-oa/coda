import re
from typing import Any, NamedTuple, Protocol

import pydantic

from coda.string import NonEmptyStr

from pydantic_core import PydanticCustomError
from pydantic_extra_types.isbn import ISBN


class Link(Protocol):
    def type(self) -> str:
        ...

    def value(self) -> str:
        ...

    def url(self) -> str:
        ...


class UserLink(NamedTuple):
    link_type: str
    link_value: str
    url_prefix: str = ""

    def type(self) -> str:
        return self.link_type

    def value(self) -> str:
        return self.link_value

    def url(self) -> str:
        return self.url_prefix + self.link_value

    def __str__(self) -> str:
        return self.link_value


class Isbn:
    __slot__ = ("_value",)
    __match_args__ = ("_value",)

    def __init__(self, isbn: str) -> None:
        try:
            raw_isbn = NonEmptyStr(isbn.replace("-", ""))
            ISBN.validate_isbn_format(raw_isbn)
            self._isbn = raw_isbn
        except PydanticCustomError:
            raise ValueError(f"{isbn} is not a valid ISBN")

    @staticmethod
    def type() -> str:
        return "ISBN"

    def value(self) -> str:
        return self._isbn

    def url(self) -> str:
        """
        URL based on PICA interface documentation found at:
        https://github.com/pro4bib/pica/blob/master/schnittstellen.md#sru
        """
        return f"https://opac.k10plus.de/DB=2.299/CMD?ACT=SRCHA&IKT=7&TRM={self}"

    def is_isbn_10(self) -> bool:
        return len(self) == 10

    def is_isbn_13(self) -> bool:
        return len(self) == 13

    def to_isbn_13(self) -> "Isbn":
        if self.is_isbn_13():
            return self

        return Isbn(ISBN.convert_isbn10_to_isbn13(self._isbn))

    def __str__(self) -> str:
        return self._isbn

    def __len__(self) -> int:
        return len(self._isbn)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Isbn):
            return False

        return self._isbn == other._isbn

    def __hash__(self) -> int:
        return hash((self._isbn,))


class Doi:
    __match_args__ = ("_doi",)

    def __init__(self, doi: str) -> None:
        self._doi = NonEmptyStr(doi).strip()
        if not self._valid():
            raise ValueError("Invalid DOI format")

    @staticmethod
    def type() -> str:
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

    def value(self) -> str:
        return self._doi

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


class Url:
    def __init__(self, url: str) -> None:
        try:
            self._url = str(pydantic.HttpUrl(url))
        except pydantic.ValidationError:
            raise ValueError(f"{url} is not a valid URL")

    @staticmethod
    def type() -> str:
        return "URL"

    def value(self) -> str:
        return self._url

    def url(self) -> str:
        return self._url

    def __str__(self) -> str:
        return self._url

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Url):
            return False
        return self._url == other._url

    def __hash__(self) -> int:
        return hash((self._url,))


_LinkTypes = {t.type(): t for t in (Doi, Isbn, Url)}


def link_types() -> list[str]:
    return list(_LinkTypes.keys())


def create_link(link_type: str, link_value: str) -> Link:
    link_constructor = _LinkTypes.get(link_type)
    if not link_constructor:
        return UserLink(link_type=link_type, link_value=link_value)

    return link_constructor(link_value)
