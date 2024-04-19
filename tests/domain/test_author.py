from typing import NewType

import pytest

from coda.orcid import Orcid
from coda.string import NonEmptyStr
from tests.test_orcid import JOSIAH_CARBERRY

AuthorId = NewType("AuthorId", int)


class Author:
    def __init__(
        self,
        id: AuthorId,
        name: str,
        email: str = "",
        orcid: Orcid | None = None,
    ) -> None:
        self.id = id
        self.name = NonEmptyStr(name)
        self.email = email
        self.orcid: Orcid | None = orcid

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Author):
            return False

        return self.id == other.id


def test__can_create_author() -> None:
    _ = Author(
        id=AuthorId(8),
        name=NonEmptyStr("John Doe"),
        email="john.doe@example.com",
        orcid=Orcid(JOSIAH_CARBERRY),
    )


def test__author_requires_name() -> None:
    with pytest.raises(ValueError):
        Author(id=AuthorId(8), name="", email="")


def test__authors_with_same_id_are_equal() -> None:
    author1 = Author(id=AuthorId(8), name="John Doe")
    author2 = Author(id=AuthorId(8), name="Jane Doe")
    author3 = Author(id=AuthorId(1), name="Jim Doe")

    assert author1 == author2
    assert author1 != author3
    assert author2 != author3
