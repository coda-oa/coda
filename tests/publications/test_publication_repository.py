from typing import Protocol

import pytest

from coda.apps.authors.services import author_create
from coda.apps.contracts.services import as_domain_object
from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.contract import PublisherId
from coda.doi import Doi
from coda.orcid import Orcid
from coda.publication import BasePublication, JournalId, Monograph, Publication, PublicationId
from coda.vocabulary import Vocabulary, VocabularyConcept
from tests import domainfactory, modelfactory, test_orcid
from tests.authors.test__author import assert_author_eq


class PublicationFactory(Protocol):
    def __call__(
        self,
        subject_area: VocabularyConcept,
        publication_type: VocabularyConcept,
        publication_id: PublicationId | None = None,
    ) -> tuple[PublicationId, BasePublication]:
        ...


def save_publication(
    subject_area: VocabularyConcept,
    publication_type: VocabularyConcept,
    publication_id: PublicationId | None = None,
) -> tuple[PublicationId, Publication]:
    journal = JournalId(modelfactory.journal().id)
    contracts = [as_domain_object(modelfactory.contract()) for _ in range(4)]
    contract_years = [domainfactory.contract_year(contract) for contract in contracts]
    publication = domainfactory.publication(
        journal=journal,
        subject_area=subject_area,
        publication_type=publication_type,
        contracts=tuple(contract_years),
        id=publication_id,
    )
    id = publication_repository.save(publication)
    return id, publication


def save_monograph(
    subject_area: VocabularyConcept,
    publication_type: VocabularyConcept,
    publication_id: PublicationId | None = None,
) -> tuple[PublicationId, Monograph]:
    publisher = modelfactory.publisher().id
    publication = domainfactory.monograph(
        publisher=PublisherId(publisher),
        subject_area=subject_area,
        publication_type=publication_type,
        id=publication_id,
    )
    id = publication_repository.save(publication)
    return id, publication


def publication_factories() -> list[PublicationFactory]:
    return [save_publication, save_monograph]


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__save_publication__get_by_id__returns_publication(
    publication_factory: PublicationFactory,
) -> None:
    concept = "1"
    subject_area_vocabulary = vocabulary_with_concepts(concept)
    publication_type_vocabulary = vocabulary_with_concepts(concept)

    id, publication = publication_factory(
        subject_area_vocabulary.get_concept(concept),
        publication_type_vocabulary.get_concept(concept),
    )

    actual = publication_repository.get_by_id(id)

    assert_publication_eq(actual, publication)


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__existing_publication__save_with_new_data__is_saved_in_database(
    publication_factory: PublicationFactory,
) -> None:
    old_concept, new_concept = "old-concept", "new-concept"
    subject_area_vocabulary = vocabulary_with_concepts(old_concept, new_concept)
    publication_type_vocabulary = vocabulary_with_concepts(old_concept, new_concept)

    existing_id, _ = publication_factory(
        subject_area_vocabulary.get_concept(old_concept),
        publication_type_vocabulary.get_concept(old_concept),
    )

    updated_id, updated = publication_factory(
        subject_area_vocabulary.get_concept(new_concept),
        publication_type_vocabulary.get_concept(new_concept),
        publication_id=existing_id,
    )

    actual = publication_repository.get_by_id(updated_id)

    assert actual is not None
    assert existing_id == updated_id
    assert_publication_eq(actual, updated)


@pytest.mark.django_db
def test__can_save_publication_with_author_that_has_existing_orcid() -> None:
    _orcid = test_orcid.JOSIAH_CARBERRY
    author = domainfactory.author()
    author.orcid = Orcid(_orcid)
    author_create(author)

    journal = JournalId(modelfactory.journal().pk)
    publication = domainfactory.publication(journal)
    publication.corresponding_author = author

    id = publication_repository.save(publication)

    assert_publication_eq(publication_repository.get_by_id(id), publication)


@pytest.mark.django_db
def test__save_publication_with_limited_vocabulary__get_by_id__returns_publication_with_limited_vocabulary() -> (
    None
):
    publication_types = vocabulary_with_concepts("1")
    subject_areas = vocabulary_with_concepts("allowed", "disallowed")

    limited = vocabulary_repository.create_limited(subject_areas.id, "Limited")
    limited.disallow("disallowed")
    vocabulary_repository.save(limited)

    id, _ = save_publication(
        subject_area=limited.get_concept("allowed"),
        publication_type=publication_types.get_concept("1"),
    )

    actual = publication_repository.get_by_id(id)

    assert actual.subject_area.vocabulary == limited.id


@pytest.mark.django_db
def test__existing_publication_with_links__save_without_links__links_are_removed() -> None:
    journal = JournalId(modelfactory.journal().pk)
    publication = domainfactory.publication(journal)
    publication.links = {Doi("10.1234/5678")}
    id = publication_repository.save(publication)

    publication.id = id
    publication.links.clear()
    publication_repository.save(publication)

    actual = publication_repository.get_by_id(id)
    assert actual.links == set()


@pytest.mark.django_db
def test__find_by_vocabulary__returns_publications_with_matching_vocabulary() -> None:
    publication_types = vocabulary_with_concepts("pub-type")
    subject_areas = vocabulary_with_concepts("sub-area")

    id, _ = save_publication(
        subject_area=subject_areas.get_concept("sub-area"),
        publication_type=publication_types.get_concept("pub-type"),
    )

    actual, *_ = publication_repository.find_publications_by_vocabulary(publication_types.id)
    assert actual.id == id

    actual, *_ = publication_repository.find_publications_by_vocabulary(subject_areas.id)
    assert actual.id == id


def vocabulary_with_concepts(*concepts: str) -> Vocabulary:
    vocabulary = vocabulary_repository.create("A Vocabulary", "1.0")
    for concept in concepts:
        vocabulary.add_concept(concept)

    vocabulary_repository.save(vocabulary)
    return vocabulary


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
