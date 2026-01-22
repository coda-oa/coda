import datetime
from itertools import zip_longest
from typing import Protocol

import pytest

from coda.apps.authors.services import author_create
from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts import mapper as contract_mapper
from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.domain.contract import ContractYear, PublisherId
from coda.domain.date import DateRange
from coda.domain.orcid import Orcid
from coda.domain.publication import (
    Authors,
    BasePublication,
    JournalId,
    Monograph,
    Publication,
    PublicationId,
)
from coda.domain.publication.links import Doi
from coda.domain.vocabulary import UnknownConcept, Vocabulary, VocabularyConcept
from tests import domainfactory, modelfactory, test_orcid
from tests.authors.test__author import assert_author_eq
from tests.contracts.test_contract_repository import assert_contract_eq


class PublicationFactory(Protocol):
    def __call__(
        self,
        subject_area: VocabularyConcept = UnknownConcept,
        publication_type: VocabularyConcept = UnknownConcept,
        publication_id: PublicationId | None = None,
    ) -> BasePublication:
        ...


def create_publication(
    subject_area: VocabularyConcept = UnknownConcept,
    publication_type: VocabularyConcept = UnknownConcept,
    publication_id: PublicationId | None = None,
) -> Publication:
    journal = JournalId(modelfactory.journal().id)
    contracts = [contract_mapper.as_domain_object(modelfactory.contract()) for _ in range(4)]
    contract_years = [domainfactory.contract_year(contract) for contract in contracts]
    publication = domainfactory.publication(
        journal=journal,
        subject_area=subject_area,
        publication_type=publication_type,
        contracts=tuple(contract_years),
        id=publication_id,
    )
    return publication


def create_monograph(
    subject_area: VocabularyConcept = UnknownConcept,
    publication_type: VocabularyConcept = UnknownConcept,
    publication_id: PublicationId | None = None,
) -> Monograph:
    publisher = modelfactory.publisher().id
    publication = domainfactory.monograph(
        publisher=PublisherId(publisher),
        subject_area=subject_area,
        publication_type=publication_type,
        id=publication_id,
    )
    return publication


def publication_factories() -> list[PublicationFactory]:
    return [create_publication, create_monograph]


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__save_publication__get_by_id__returns_publication(
    publication_factory: PublicationFactory,
) -> None:
    concept = "1"
    subject_area_vocabulary = vocabulary_with_concepts(concept)
    publication_type_vocabulary = vocabulary_with_concepts(concept)

    publication = publication_factory(
        subject_area_vocabulary.get_concept(concept),
        publication_type_vocabulary.get_concept(concept),
    )
    id = publication_repository.create(publication)

    actual = publication_repository.get_by_id(id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__create_publication__create_again__raises_error(
    publication_factory: PublicationFactory,
) -> None:
    concept = "1"
    subject_area_vocabulary = vocabulary_with_concepts(concept)
    publication_type_vocabulary = vocabulary_with_concepts(concept)

    publication = publication_factory(
        subject_area_vocabulary.get_concept(concept),
        publication_type_vocabulary.get_concept(concept),
    )
    publication.id = publication_repository.create(publication)

    with pytest.raises(publication_repository.PublicationAlreadyCreated):
        publication_repository.create(publication)


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test_publication_with_same_contract_in_different_years__create__saves_with_all_contracts(
    publication_factory: PublicationFactory,
) -> None:
    contract = domainfactory.contract(period=DateRange.create(start=datetime.date(2023, 1, 1)))
    contract.id = contract_repository.create(contract)
    first = contract.in_year(2023)
    second = contract.in_year(2024)

    publication = publication_factory()
    publication.contracts = (second, first)

    id = publication_repository.create(publication)

    actual = publication_repository.get_by_id(id)
    assert_publication_eq(actual, publication)


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__existing_publication__update_with_new_data__is_saved_in_database(
    publication_factory: PublicationFactory,
) -> None:
    old_concept, new_concept = "old-concept", "new-concept"
    subject_area_vocabulary = vocabulary_with_concepts(old_concept, new_concept)
    publication_type_vocabulary = vocabulary_with_concepts(old_concept, new_concept)

    existing_publication = publication_factory(
        subject_area_vocabulary.get_concept(old_concept),
        publication_type_vocabulary.get_concept(old_concept),
    )
    existing_id = publication_repository.create(existing_publication)

    updated = publication_factory(
        subject_area_vocabulary.get_concept(new_concept),
        publication_type_vocabulary.get_concept(new_concept),
        publication_id=existing_id,
    )
    publication_repository.update(updated)

    actual = publication_repository.get_by_id(existing_id)
    assert_publication_eq(actual, updated)
    assert len(publication_repository.all()) == 1


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__unsaved_publication__update__raises_error(
    publication_factory: PublicationFactory,
) -> None:
    concept = "1"
    subject_area_vocabulary = vocabulary_with_concepts(concept)
    publication_type_vocabulary = vocabulary_with_concepts(concept)

    publication = publication_factory(
        subject_area_vocabulary.get_concept(concept),
        publication_type_vocabulary.get_concept(concept),
    )

    with pytest.raises(publication_repository.UnsavedPublication):
        publication_repository.update(publication)


@pytest.mark.django_db
@pytest.mark.parametrize("publication_factory", publication_factories())
def test__publication_with_same_contract_in_different_years__update_with_one_contract_removed__removes_one_contract(
    publication_factory: PublicationFactory,
) -> None:
    contract = domainfactory.contract(period=DateRange.create(start=datetime.date(2023, 1, 1)))
    contract.id = contract_repository.create(contract)
    first = contract.in_year(2023)
    second = contract.in_year(2024)

    publication = publication_factory()
    publication.contracts = (first, second)
    id = publication_repository.create(publication)

    updated = publication_factory(publication_id=id)
    updated.contracts = (first,)

    publication_repository.update(updated)

    actual = publication_repository.get_by_id(id)
    assert_publication_eq(actual, updated)


@pytest.mark.django_db
def test__can_save_publication_with_author_that_has_existing_orcid() -> None:
    _orcid = test_orcid.JOSIAH_CARBERRY
    author = domainfactory.author()
    author.orcid = Orcid(_orcid)
    author_create(author)

    journal = JournalId(modelfactory.journal().pk)
    publication = domainfactory.publication(journal)
    publication.relevant_authors = Authors([author])

    id = publication_repository.create(publication)

    assert_publication_eq(publication_repository.get_by_id(id), publication)


@pytest.mark.django_db
def test__save_publication_with_limited_vocabulary__get_by_id__returns_publication_with_limited_vocabulary() -> (
    None
):
    publication_types = vocabulary_with_concepts("1")
    subject_areas = vocabulary_with_concepts("allowed", "disallowed")

    assert subject_areas.id is not None  # Repository create should assign ID
    limited = vocabulary_repository.create_limited(subject_areas.id, "Limited")
    limited.disallow("disallowed")
    vocabulary_repository.save(limited)

    publication = create_publication(
        subject_area=limited.get_concept("allowed"),
        publication_type=publication_types.get_concept("1"),
    )
    id = publication_repository.create(publication)

    actual = publication_repository.get_by_id(id)
    assert actual.subject_area.vocabulary == limited.id


@pytest.mark.django_db
def test__existing_publication_with_links__save_without_links__links_are_removed() -> None:
    journal = JournalId(modelfactory.journal().pk)
    publication = domainfactory.publication(journal)
    publication.links = {Doi("10.1234/5678")}
    publication.id = publication_repository.create(publication)

    publication.links.clear()
    publication_repository.update(publication)

    actual = publication_repository.get_by_id(publication.id)
    assert actual.links == set()


@pytest.mark.django_db
def test__find_by_vocabulary__returns_publications_with_matching_vocabulary() -> None:
    publication_types = vocabulary_with_concepts("pub-type")
    subject_areas = vocabulary_with_concepts("sub-area")

    publication = create_publication(
        subject_area=subject_areas.get_concept("sub-area"),
        publication_type=publication_types.get_concept("pub-type"),
    )
    id = publication_repository.create(publication)

    assert publication_types.id is not None  # Repository create should assign ID
    assert subject_areas.id is not None  # Repository create should assign ID

    actual, *_ = publication_repository.find_publications_by_vocabulary(publication_types.id)
    assert actual.id == id

    actual, *_ = publication_repository.find_publications_by_vocabulary(subject_areas.id)
    assert actual.id == id


@pytest.mark.django_db
def test__can_save_publication_with_unknown_concept() -> None:
    publication = create_publication(
        subject_area=UnknownConcept,
        publication_type=UnknownConcept,
    )
    id = publication_repository.create(publication)

    actual = publication_repository.get_by_id(id)
    assert_publication_eq(actual, publication)


def vocabulary_with_concepts(*concepts: str) -> Vocabulary:
    vocabulary = vocabulary_repository.create("A Vocabulary", "1.0")
    for concept in concepts:
        vocabulary.add_concept(concept)

    vocabulary_repository.save(vocabulary)
    assert vocabulary.id is not None  # Repository create/save should assign ID
    return vocabulary


def assert_base_publication_eq(actual: BasePublication, expected: BasePublication) -> None:
    assert actual.title == expected.title
    assert actual.other_authors == expected.other_authors
    assert actual.license == expected.license
    assert actual.publication_type == expected.publication_type
    assert actual.subject_area == expected.subject_area
    assert actual.open_access_type == expected.open_access_type
    assert actual.publication_state == expected.publication_state
    assert actual.links == expected.links

    for actual_contract, expected_contract in zip_longest(actual.contracts, expected.contracts):
        assert_contract_year_eq(actual_contract, expected_contract)

    for actual_author, expected_author in zip_longest(
        actual.relevant_authors, expected.relevant_authors
    ):
        assert_author_eq(actual_author, expected_author)


def assert_contract_year_eq(actual: ContractYear, expected: ContractYear) -> None:
    assert actual.contract_id == expected.contract_id
    assert_contract_eq(actual.contract, expected.contract)
    assert actual.year == expected.year


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
