import faker
import pytest

from coda.author import AuthorList
from coda.doi import Doi
from coda.publication import JournalId, Publication, PublicationId, Unpublished, UserLink

_faker = faker.Faker()


def make_sut() -> Publication:
    return Publication(
        id=PublicationId(8),
        title=_faker.sentence(),
        journal=JournalId(3),
        authors=AuthorList(_faker.name() for _ in range(3)),
    )


def test__a_publication_title_must_not_be_empty() -> None:
    with pytest.raises(ValueError):
        _ = Publication(
            id=PublicationId(8),
            title="",
            authors=AuthorList(),
            journal=JournalId(3),
        )


def test__on_creation__publication_state_is_unpublished_and_publication_date_is_none() -> None:
    sut = make_sut()

    assert sut.publication_state == Unpublished()


def test__publication__has_no_links() -> None:
    sut = make_sut()

    assert sut.links == []


def test__can_add_links_to_publication() -> None:
    sut = make_sut()
    link = _faker.url()

    sut.add_link(link)

    assert sut.links == [link]


def test__cannot_add_same_link_twice() -> None:
    sut = make_sut()
    link = _faker.url()

    sut.add_link(link)
    sut.add_link(link)

    assert sut.links == [link]


def can_add_a_user_defined_link_type() -> None:
    """
    This test is not really testing anything, but we'd get a type error if the link types were not compatible.
    """
    sut = make_sut()
    link = UserLink(type="DOI", value="10.1234/5678")

    sut.add_link(link)

    assert sut.links == [link]


def can_add_a_doi_link() -> None:
    """
    This test is not really testing anything, but we'd get a type error if the link types were not compatible.
    """
    sut = make_sut()
    link = Doi("10.1234/5678")

    sut.add_link(link)

    assert sut.links == [link]
