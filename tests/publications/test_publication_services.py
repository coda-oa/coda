import pytest

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.services import get_by_id, publication_create, publication_update
from coda.author import AuthorId
from coda.publication import JournalId, Publication, PublicationId
from tests import domainfactory, dtofactory, modelfactory


@pytest.fixture
def author() -> Author:
    return modelfactory.author()


@pytest.fixture
def journal() -> Journal:
    return modelfactory.journal()


@pytest.fixture(autouse=True)
def linktypes() -> None:
    dtofactory.link_dtos()


@pytest.mark.django_db
def test__create_publication__creates_a_publication_based_on_given_data(
    author: Author, journal: Journal
) -> None:
    publication = domainfactory.publication(JournalId(journal.pk))
    new_id = publication_create(publication, AuthorId(author.pk))

    actual = get_by_id(new_id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__update_publication__updates_publication_based_on_given_data(
    author: Author, journal: Journal
) -> None:
    publication = domainfactory.publication(JournalId(journal.pk))
    new_id = publication_create(publication, AuthorId(author.pk))

    new_journal = modelfactory.journal()
    new_publication = domainfactory.publication(JournalId(new_journal.pk), id=PublicationId(new_id))

    publication_update(new_publication)

    actual = get_by_id(new_id)
    assert_publication_eq(actual, new_publication)


def assert_publication_eq(actual: Publication, expected: Publication) -> None:
    assert actual.title == expected.title
    assert actual.authors == expected.authors
    assert actual.journal == expected.journal
    assert actual.license == expected.license
    assert actual.open_access_type == expected.open_access_type
    assert actual.publication_state == expected.publication_state
    assert actual.links == expected.links
