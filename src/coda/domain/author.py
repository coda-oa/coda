import enum
import re
from collections.abc import Iterable, Iterator
from typing import Any, NewType

from coda.domain import errors
from coda.domain.orcid import Orcid
from coda.domain.string import NonEmptyStr

AuthorId = NewType("AuthorId", int)
InstitutionId = NewType("InstitutionId", int)


class NoEmailForCorrespondingAuthor(errors.DomainError):
    def __init__(self, author_name: str) -> None:
        super().__init__(f"{author_name} is the corresponding author, but does not have an email")


class Role(enum.Enum):
    SUBMITTER = "Submitter"
    CO_AUTHOR = "Co-author"
    CORRESPONDING_AUTHOR = "Corresponding author"
    SUBMITTING_CORRESPONDING_AUTHOR = "Submitting corresponding author"

    def is_corresponding_role(self) -> bool:
        return self in (Role.CORRESPONDING_AUTHOR, Role.SUBMITTING_CORRESPONDING_AUTHOR)

    def is_submitting_role(self) -> bool:
        return self in (Role.SUBMITTER, Role.SUBMITTING_CORRESPONDING_AUTHOR)


class Author:
    """
    Domain entity representing an author.

    Use Author.new() to create new authors with validation.
    Use Author.restore() to load existing authors from the database.
    Direct instantiation is discouraged - use the factory methods instead.
    """

    def __init__(
        self,
        id: AuthorId | None,
        name: NonEmptyStr,
        orcid: Orcid | None = None,
        affiliation: InstitutionId | None = None,
        _email: str = "",
        _role: Role = Role.CO_AUTHOR,
        *,
        _restore: bool = False,
    ) -> None:
        """
        Initialize an Author instance.

        Args:
            id: Unique identifier for the author (None for new authors)
            name: Author's name (must be non-empty)
            orcid: Optional ORCID identifier
            affiliation: Optional institution affiliation ID
            _email: Author's email address (private field)
            _role: Author's role (private field)
            _restore: Internal flag to bypass validation when loading from database.
                     WARNING: Do not use directly. Use Author.new() or Author.restore().
                     This flag exists to allow loading legacy data that may not meet
                     current validation rules.

        Raises:
            NoEmailForCorrespondingAuthor: If _restore=False and the author is a
                corresponding author without an email address.
        """
        self.id = id
        self.name = name
        self.orcid = orcid
        self.affiliation = affiliation
        self._email = _email
        self._role = _role

        # Validate business rules only when not restoring legacy data
        if not _restore and _role.is_corresponding_role() and not _email:
            raise NoEmailForCorrespondingAuthor(name)

    @classmethod
    def new(
        cls,
        name: NonEmptyStr,
        email: str = "",
        orcid: Orcid | None = None,
        affiliation: InstitutionId | None = None,
        role: Role = Role.CO_AUTHOR,
    ) -> "Author":
        """
        Create a new author with validation.

        This method enforces all business rules, including requiring an email
        for corresponding authors.

        Args:
            name: Author's name (must be non-empty)
            email: Author's email address (required for corresponding authors)
            orcid: Optional ORCID identifier
            affiliation: Optional institution affiliation ID
            role: Author's role (default: CO_AUTHOR)

        Returns:
            A new Author instance with id=None

        Raises:
            NoEmailForCorrespondingAuthor: If the role is corresponding author
                and email is empty.
        """
        return cls(
            id=None,
            name=name,
            orcid=orcid,
            affiliation=affiliation,
            _email=email,
            _role=role,
            _restore=False,
        )

    @classmethod
    def restore(
        cls,
        id: AuthorId | None,
        name: NonEmptyStr,
        email: str = "",
        orcid: Orcid | None = None,
        affiliation: InstitutionId | None = None,
        role: Role = Role.CO_AUTHOR,
    ) -> "Author":
        """
        Restore an existing author from the database without validation.

        This method bypasses validation to allow loading legacy data that may
        not meet current business rules (e.g., corresponding authors without emails).
        Property setters will still enforce validation on subsequent updates.

        Args:
            id: Author's database ID
            name: Author's name
            email: Author's email address
            orcid: Optional ORCID identifier
            affiliation: Optional institution affiliation ID
            role: Author's role

        Returns:
            An Author instance restored from the database
        """
        return cls(
            id=id,
            name=name,
            orcid=orcid,
            affiliation=affiliation,
            _email=email,
            _role=role,
            _restore=True,
        )

    @property
    def email(self) -> str:
        return self._email

    @email.setter
    def email(self, value: str) -> None:
        if self.role.is_corresponding_role() and not value:
            raise NoEmailForCorrespondingAuthor(self.name)

        self._email = value

    @property
    def role(self) -> Role:
        return self._role

    @role.setter
    def role(self, value: Role) -> None:
        if value.is_corresponding_role() and not self.email:
            raise NoEmailForCorrespondingAuthor(self.name)

        self._role = value

    def is_corresponding_author(self) -> bool:
        return self.role.is_corresponding_role()

    def is_submitter(self) -> bool:
        return self.role.is_submitting_role()

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
    return re.sub(r"([a-z])([A-Z])(?<!\sPhD)", r"\1 \2", author)


def _replace_broken_umlaute(author: str) -> str:
    return author.replace(" ̈u", "ü").replace(" ̈o", "ö").replace(" ̈a", "ä")


class AuthorNames(Iterable[str]):
    def __init__(self, authors: Iterable[str] = ()) -> None:
        self._authors = tuple(authors)

    @classmethod
    def from_str(cls, authors: str) -> "AuthorNames":
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
