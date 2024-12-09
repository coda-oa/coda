from typing import cast

import pytest

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.apps.publications.services.publications import publication_create, publication_update
from coda.author import AuthorId
from coda.contract import ContractId
from coda.publication import BasePublication, JournalId, Monograph, Publication, PublicationId
from coda.vocabulary import UnknownConcept
from tests import domainfactory, modelfactory
from tests.authors.test__author import assert_author_eq


@pytest.fixture
def author() -> Author:
    return modelfactory.author()


@pytest.fixture
def journal() -> Journal:
    return modelfactory.journal()


@pytest.mark.django_db
def test__create_publication__creates_a_publication_based_on_given_data(journal: Journal) -> None:
    pub_types = vocabulary_repository.create("publication_type", "1.0")
    pub_types.add_concept("pub-type-1", "Pub Type 1")
    vocabulary_repository.save(pub_types)

    subject_areas = vocabulary_repository.create("subject_area", "1.0")
    subject_areas.add_concept("subject-area-1", "Subject Area 1")
    vocabulary_repository.save(subject_areas)

    contracts = (ContractId(modelfactory.contract().pk), ContractId(modelfactory.contract().pk))

    publication = domainfactory.publication(
        JournalId(journal.pk),
        publication_type=pub_types.get_concept("pub-type-1"),
        subject_area=subject_areas.get_concept("subject-area-1"),
        contracts=contracts,
    )
    new_id = publication_create(publication)

    actual = publication_repository.get_by_id(new_id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__can_create_publication_with_unknown_publication_type(journal: Journal) -> None:
    publication = domainfactory.publication(JournalId(journal.pk), publication_type=UnknownConcept)
    new_id = publication_create(publication)

    actual = publication_repository.get_by_id(new_id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__update_publication__updates_publication_based_on_given_data(journal: Journal) -> None:
    pub_types = vocabulary_repository.create("publication_type", "1.0")
    pub_types.add_concept("old-pub-type", "Pub Type 1")
    pub_types.add_concept("new-pub-type", "Pub Type 1")
    vocabulary_repository.save(pub_types)

    subject_areas = vocabulary_repository.create("subject_area", "1.0")
    subject_areas.add_concept("old-subject-area", "Subject Area 1")
    subject_areas.add_concept("new-subject-area", "Subject Area 1")
    vocabulary_repository.save(subject_areas)

    publication = domainfactory.publication(
        JournalId(journal.pk),
        publication_type=pub_types.get_concept("old-pub-type"),
        subject_area=subject_areas.get_concept("old-subject-area"),
    )
    new_id = publication_create(publication)
    new_journal = modelfactory.journal()
    new_publication = domainfactory.publication(
        JournalId(new_journal.pk),
        publication_type=pub_types.get_concept("new-pub-type"),
        subject_area=subject_areas.get_concept("new-subject-area"),
        id=PublicationId(new_id),
    )

    publication_update(new_publication)

    actual = publication_repository.get_by_id(new_id)
    assert_publication_eq(actual, new_publication)


@pytest.mark.django_db
def test__update_publication__existing_author_gets_updated_inplace() -> None:
    publication = domainfactory.publication(JournalId(modelfactory.journal().pk))
    publication_id = publication_create(publication)
    created = publication_repository.get_by_id(publication_id)
    expected_author_id = cast(AuthorId, created.corresponding_author.id)

    new_publication = domainfactory.publication(
        JournalId(modelfactory.journal().pk), id=PublicationId(publication_id)
    )

    publication_update(new_publication)

    actual = publication_repository.get_by_id(publication_id)
    assert actual.corresponding_author.id == expected_author_id


@pytest.mark.django_db
def test__can_update_publication_with_unknown_concepts(journal: Journal) -> None:
    pub_types = vocabulary_repository.create("publication_type", "1.0")
    pub_types.add_concept("old-pub-type", "Pub Type 1")
    vocabulary_repository.save(pub_types)

    subject_areas = vocabulary_repository.create("subject_area", "1.0")
    subject_areas.add_concept("old-subject-area", "Subject Area 1")
    vocabulary_repository.save(subject_areas)

    publication = domainfactory.publication(
        JournalId(journal.pk),
        publication_type=pub_types.get_concept("old-pub-type"),
        subject_area=subject_areas.get_concept("old-subject-area"),
    )
    new_id = publication_create(publication)

    new_journal = modelfactory.journal()
    new_publication = domainfactory.publication(
        JournalId(new_journal.pk),
        publication_type=UnknownConcept,
        subject_area=UnknownConcept,
        id=PublicationId(new_id),
    )

    publication_update(new_publication)

    actual = publication_repository.get_by_id(new_id)
    assert_publication_eq(actual, new_publication)


@pytest.mark.django_db
def test__can_update_publication_with_contracts(journal: Journal) -> None:
    contracts = [modelfactory.contract(), modelfactory.contract()]
    publication = domainfactory.publication(JournalId(journal.pk))
    new_id = publication_create(publication)

    expected = domainfactory.publication(
        JournalId(journal.pk),
        contracts=tuple([ContractId(c.pk) for c in contracts]),
        id=PublicationId(new_id),
    )

    publication_update(expected)

    actual = publication_repository.get_by_id(new_id)
    assert_publication_eq(actual, expected)


def assert_base_publication_eq(actual: BasePublication, expected: BasePublication) -> None:
    assert actual.title == expected.title
    assert actual.authors == expected.authors
    assert actual.license == expected.license
    assert actual.publication_type == expected.publication_type
    assert actual.subject_area == expected.subject_area
    assert actual.open_access_type == expected.open_access_type
    assert actual.publication_state == expected.publication_state
    assert actual.contracts == expected.contracts
    assert actual.links == expected.links
    assert_author_eq(actual.corresponding_author, expected.corresponding_author)


def assert_monograph_eq(actual: Monograph, expected: Monograph) -> None:
    assert_base_publication_eq(actual, expected)
    assert actual.publisher == expected.publisher


def assert_article_eq(actual: Publication, expected: Publication) -> None:
    assert_base_publication_eq(actual, expected)
    assert actual.journal == expected.journal


def assert_publication_eq(actual: BasePublication, expected: BasePublication) -> None:
    match actual, expected:
        case Monograph(), Monograph():
            assert_monograph_eq(actual, expected)
        case Publication(), Publication():
            assert_article_eq(actual, expected)
        case _:
            raise AssertionError(
                f"Mismatched publication types: {type(actual)} and {type(expected)}"
            )
