import pytest

from coda.domain.author import Author, AuthorId, Role
from coda.domain.orcid import Orcid
from coda.domain.string import NonEmptyStr
from tests.test_orcid import JOSIAH_CARBERRY


def test__can_create_author() -> None:
    _ = Author.restore(
        id=AuthorId(8),
        name=NonEmptyStr("John Doe"),
        email="john.doe@example.com",
        orcid=Orcid(JOSIAH_CARBERRY),
    )


def test__authors_with_same_id_are_equal() -> None:
    author1 = Author.restore(id=AuthorId(8), name=NonEmptyStr("John Doe"))
    author2 = Author.restore(id=AuthorId(8), name=NonEmptyStr("Jane Doe"))
    author3 = Author.restore(id=AuthorId(1), name=NonEmptyStr("Jim Doe"))

    assert author1 == author2
    assert author1 != author3
    assert author2 != author3


def test__author_with_submitting_role__is_submitter() -> None:
    author = Author.new(name=NonEmptyStr("John Doe"), role=Role.SUBMITTER)
    assert author.is_submitter()

    author = Author.new(
        name=NonEmptyStr("John Doe"),
        role=Role.SUBMITTING_CORRESPONDING_AUTHOR,
        email="j.doe@example.com",
    )
    assert author.is_submitter()


@pytest.mark.parametrize("role", (Role.CORRESPONDING_AUTHOR, Role.SUBMITTING_CORRESPONDING_AUTHOR))
def test__new_author__is_corresponding_author__must_have_an_email(role: Role) -> None:
    with pytest.raises(ValueError):
        _ = Author.new(NonEmptyStr("John Doe"), role=role)

    sut = Author.new(NonEmptyStr("John Doe"), "j.doe@example.com", role=role)
    with pytest.raises(ValueError):
        sut.email = ""

    sut = Author.new(NonEmptyStr("John Doe"), "")
    with pytest.raises(ValueError):
        sut.role = role


@pytest.mark.parametrize("role", (Role.CORRESPONDING_AUTHOR, Role.SUBMITTING_CORRESPONDING_AUTHOR))
def test__restored_corresponding_author_without_email__setting_role_or_email__raises_error(
    role: Role,
) -> None:
    author = Author.restore(
        id=AuthorId(1),
        name=NonEmptyStr("John Doe"),
        email="",
        role=role,
    )

    with pytest.raises(ValueError):
        author.email = ""

    with pytest.raises(ValueError):
        author.role = role
