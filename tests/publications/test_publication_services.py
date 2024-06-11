import pytest

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Concept
from coda.apps.publications.services import get_by_id, publication_create, publication_update
from coda.author import AuthorId
from coda.publication import (
    JournalId,
    Publication,
    PublicationId,
    PublicationType,
    UnknownPublicationType,
)
from tests import domainfactory, modelfactory


@pytest.fixture
def author() -> Author:
    return modelfactory.author()


@pytest.fixture
def journal() -> Journal:
    return modelfactory.journal()


@pytest.mark.django_db
def test__create_publication__creates_a_publication_based_on_given_data(
    author: Author, journal: Journal
) -> None:
    concept = modelfactory.concept()
    publication = domainfactory.publication(
        JournalId(journal.pk), publication_type=publication_type_from_concept(concept)
    )
    new_id = publication_create(publication, AuthorId(author.pk))

    actual = get_by_id(new_id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__can_create_publication_with_unknown_publication_type(
    author: Author, journal: Journal
) -> None:
    publication = domainfactory.publication(
        JournalId(journal.pk), publication_type=UnknownPublicationType
    )
    new_id = publication_create(publication, AuthorId(author.pk))

    actual = get_by_id(new_id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__update_publication__updates_publication_based_on_given_data(
    author: Author, journal: Journal
) -> None:
    old_concept = modelfactory.concept()
    publication = domainfactory.publication(
        JournalId(journal.pk), publication_type=publication_type_from_concept(old_concept)
    )
    new_id = publication_create(publication, AuthorId(author.pk))

    new_concept = modelfactory.concept()
    new_journal = modelfactory.journal()
    new_publication = domainfactory.publication(
        JournalId(new_journal.pk),
        publication_type=publication_type_from_concept(new_concept),
        id=PublicationId(new_id),
    )

    publication_update(new_publication)

    actual = get_by_id(new_id)
    assert_publication_eq(actual, new_publication)


@pytest.mark.django_db
def test__can_update_publication_with_unknown_publication_type(
    author: Author, journal: Journal
) -> None:
    old_concept = modelfactory.concept()
    publication = domainfactory.publication(
        JournalId(journal.pk), publication_type=publication_type_from_concept(old_concept)
    )
    new_id = publication_create(publication, AuthorId(author.pk))

    new_journal = modelfactory.journal()
    new_publication = domainfactory.publication(
        JournalId(new_journal.pk),
        publication_type=UnknownPublicationType,
        id=PublicationId(new_id),
    )

    publication_update(new_publication)

    actual = get_by_id(new_id)
    assert_publication_eq(actual, new_publication)


def publication_type_from_concept(concept: Concept) -> PublicationType:
    return PublicationType(concept.concept_id)


def assert_publication_eq(actual: Publication, expected: Publication) -> None:
    assert actual.title == expected.title
    assert actual.authors == expected.authors
    assert actual.journal == expected.journal
    assert actual.license == expected.license
    assert actual.publication_type == expected.publication_type
    assert actual.open_access_type == expected.open_access_type
    assert actual.publication_state == expected.publication_state
    assert actual.links == expected.links
