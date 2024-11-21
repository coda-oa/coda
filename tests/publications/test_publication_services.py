from typing import cast

import pytest

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Concept
from coda.apps.publications.services.publications import (
    get_by_id,
    publication_create,
    publication_update,
)
from coda.author import AuthorId
from coda.contract import ContractId
from coda.publication import JournalId, Publication, PublicationId
from coda.vocabulary import ConceptId, UnknownConcept, VocabularyConcept, VocabularyId
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
    publication_type_concept = modelfactory.concept()
    subject_area_concept = modelfactory.concept()
    contracts = (ContractId(modelfactory.contract().pk), ContractId(modelfactory.contract().pk))

    publication = domainfactory.publication(
        JournalId(journal.pk),
        publication_type=as_domain_concept(publication_type_concept),
        subject_area=as_domain_concept(subject_area_concept),
        contracts=contracts,
    )
    new_id = publication_create(publication)

    actual = get_by_id(new_id)
    assert_publication_eq(actual, publication)


def as_domain_concept(c: Concept) -> VocabularyConcept:
    return VocabularyConcept(id=ConceptId(c.concept_id), vocabulary=VocabularyId(c.vocabulary_id))


@pytest.mark.django_db
def test__can_create_publication_with_unknown_publication_type(journal: Journal) -> None:
    publication = domainfactory.publication(JournalId(journal.pk), publication_type=UnknownConcept)
    new_id = publication_create(publication)

    actual = get_by_id(new_id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__update_publication__updates_publication_based_on_given_data(journal: Journal) -> None:
    old_pub_type = modelfactory.concept()
    old_subject_area = modelfactory.concept()

    publication = domainfactory.publication(
        JournalId(journal.pk),
        publication_type=as_domain_concept(old_pub_type),
        subject_area=as_domain_concept(old_subject_area),
    )
    new_id = publication_create(publication)

    new_pub_type = modelfactory.concept()
    new_subject_area = modelfactory.concept()
    new_journal = modelfactory.journal()
    new_publication = domainfactory.publication(
        JournalId(new_journal.pk),
        publication_type=as_domain_concept(new_pub_type),
        subject_area=as_domain_concept(new_subject_area),
        id=PublicationId(new_id),
    )

    publication_update(new_publication)

    actual = get_by_id(new_id)
    assert_publication_eq(actual, new_publication)


@pytest.mark.django_db
def test__update_publication__existing_author_gets_updated_inplace() -> None:
    publication = domainfactory.publication(JournalId(modelfactory.journal().pk))
    publication_id = publication_create(publication)
    created = get_by_id(publication_id)
    expected_author_id = cast(AuthorId, created.corresponding_author.id)

    new_publication = domainfactory.publication(
        JournalId(modelfactory.journal().pk), id=PublicationId(publication_id)
    )

    publication_update(new_publication)

    actual = get_by_id(publication_id)
    assert actual.corresponding_author.id == expected_author_id


@pytest.mark.django_db
def test__can_update_publication_with_unknown_concepts(journal: Journal) -> None:
    old_pub_type = modelfactory.concept()
    old_subject_area = modelfactory.concept()
    publication = domainfactory.publication(
        JournalId(journal.pk),
        publication_type=as_domain_concept(old_pub_type),
        subject_area=as_domain_concept(old_subject_area),
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

    actual = get_by_id(new_id)
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

    actual = get_by_id(new_id)
    assert_publication_eq(actual, expected)


def assert_publication_eq(actual: Publication, expected: Publication) -> None:
    assert actual.title == expected.title
    assert actual.authors == expected.authors
    assert actual.journal == expected.journal
    assert actual.license == expected.license
    assert actual.publication_type == expected.publication_type
    assert actual.subject_area == expected.subject_area
    assert actual.open_access_type == expected.open_access_type
    assert actual.publication_state == expected.publication_state
    assert actual.contracts == expected.contracts
    assert actual.links == expected.links
    assert_author_eq(actual.corresponding_author, expected.corresponding_author)
