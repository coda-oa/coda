from coda.domain.author import Author, AuthorId, Role
from coda.domain.orcid import Orcid
from coda.domain.string import NonEmptyStr
from tests.test_orcid import JOSIAH_CARBERRY


def test__can_create_author() -> None:
    _ = Author(
        id=AuthorId(8),
        name=NonEmptyStr("John Doe"),
        email="john.doe@example.com",
        orcid=Orcid(JOSIAH_CARBERRY),
    )


def test__authors_with_same_id_are_equal() -> None:
    author1 = Author(id=AuthorId(8), name=NonEmptyStr("John Doe"))
    author2 = Author(id=AuthorId(8), name=NonEmptyStr("Jane Doe"))
    author3 = Author(id=AuthorId(1), name=NonEmptyStr("Jim Doe"))

    assert author1 == author2
    assert author1 != author3
    assert author2 != author3


def test__author_with_submitting_role__is_submitter() -> None:
    author = Author.new(name=NonEmptyStr("John Doe"), role=Role.SUBMITTER)
    assert author.is_submitter()

    author = Author.new(name=NonEmptyStr("John Doe"), role=Role.SUBMITTING_CORRESPONDING_AUTHOR)
    assert author.is_submitter()
