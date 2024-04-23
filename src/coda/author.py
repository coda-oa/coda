import re
from typing import NewType

from coda.orcid import Orcid
from coda.string import NonEmptyStr

AuthorId = NewType("AuthorId", int)


class Author:
    def __init__(
        self,
        id: AuthorId,
        name: NonEmptyStr,
        email: str = "",
        orcid: Orcid | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.email = email
        self.orcid: Orcid | None = orcid

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Author):
            return False

        return self.id == other.id


def _parse_line(line: str, /, reverse_names: bool) -> list[str]:
    line = line.strip().removeprefix("and ").removesuffix(" and")
    if reverse_names:
        split_authors_by_semicolon = map(str.strip, line.split(";"))
        split_names_by_comma = [x.split(",") for x in split_authors_by_semicolon]
        reversed_names = [reversed(x) for x in split_names_by_comma]
        author_name_list = [" ".join(x).strip() for x in reversed_names]
    else:
        sep = "," if "," in line else ";"
        line = line.replace(", and ", sep).replace(" and ", sep)
        author_name_list = [*map(str.strip, line.split(sep))]

    return author_name_list


def _insert_missing_space(author: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", author)


def _replace_broken_umlaute(author: str) -> str:
    return author.replace(" ̈u", "ü").replace(" ̈o", "ö").replace(" ̈a", "ä")


class AuthorList(list[str]):
    @classmethod
    def from_str(cls, authors: str) -> "AuthorList":
        authors = _insert_missing_space(authors)
        authors = _replace_broken_umlaute(authors)
        author_lines = authors.strip().splitlines()
        reverse = "," in authors and ";" in authors
        return cls(
            author
            for line in author_lines
            for author in _parse_line(line, reverse_names=reverse)
            if author
        )

    def __str__(self) -> str:
        return ", ".join(self)
