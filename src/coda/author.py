import enum
import re
from typing import Any, NamedTuple, NewType
from collections.abc import Iterable, Iterator

from coda.orcid import Orcid
from coda.string import NonEmptyStr

AuthorId = NewType("AuthorId", int)
InstitutionId = NewType("InstitutionId", int)


class Role(enum.Enum):
    SUBMITTER = "Submitter"
    CO_AUTHOR = "Co-author"
    CORRESPONDING_AUTHOR = "Corresponding author"


class Author(NamedTuple):
    id: AuthorId | None
    name: NonEmptyStr
    email: str = ""
    orcid: Orcid | None = None
    affiliation: InstitutionId | None = None
    roles: frozenset[Role] = frozenset()

    @classmethod
    def new(
        cls,
        name: NonEmptyStr,
        email: str,
        orcid: Orcid | None = None,
        affiliation: InstitutionId | None = None,
        roles: Iterable[Role] = (),
    ) -> "Author":
        return cls(
            id=None,
            name=name,
            email=email,
            orcid=orcid,
            affiliation=affiliation,
            roles=frozenset(roles),
        )

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


class AuthorList(Iterable[str]):
    def __init__(self, authors: Iterable[str] = ()) -> None:
        self._authors = tuple(authors)

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

    def __iter__(self) -> Iterator[str]:
        return iter(self._authors)

    def __str__(self) -> str:
        return ", ".join(self._authors)

    def __repr__(self) -> str:
        return "AuthorList([{}])".format(", ".join(repr(x) for x in self._authors))

    def __eq__(self, other: Any) -> bool:
        return all(my_author == other_author for my_author, other_author in zip(self, other))
