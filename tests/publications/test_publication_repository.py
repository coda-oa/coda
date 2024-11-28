import pytest

from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.publication import JournalId, Publication, PublicationId
from coda.vocabulary import VocabularyConcept, Vocabulary
from tests import domainfactory, modelfactory
from tests.publications.test_publication_services import assert_publication_eq


@pytest.mark.django_db
def test__save_publication__get_by_id__returns_publication() -> None:
    concept = "1"
    subject_area_vocabulary = vocabulary_with_concepts(concept)
    publication_type_vocabulary = vocabulary_with_concepts(concept)

    id, publication = save_publication(
        subject_area_vocabulary.get_concept(concept),
        publication_type_vocabulary.get_concept(concept),
    )

    actual = publication_repository.get_by_id(id)

    assert_publication_eq(actual, publication)


@pytest.mark.django_db
def test__existing_publication__save_with_new_data__is_saved_in_database() -> None:
    old_concept, new_concept = "old-concept", "new-concept"
    subject_area_vocabulary = vocabulary_with_concepts(old_concept, new_concept)
    publication_type_vocabulary = vocabulary_with_concepts(old_concept, new_concept)

    existing_id, _ = save_publication(
        subject_area_vocabulary.get_concept(old_concept),
        publication_type_vocabulary.get_concept(old_concept),
    )

    updated_id, updated = save_publication(
        subject_area_vocabulary.get_concept(new_concept),
        publication_type_vocabulary.get_concept(new_concept),
        publication_id=existing_id,
    )

    actual = publication_repository.get_by_id(updated_id)

    assert actual is not None
    assert existing_id == updated_id
    assert_publication_eq(actual, updated)


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


def save_publication(
    subject_area: VocabularyConcept,
    publication_type: VocabularyConcept,
    publication_id: PublicationId | None = None,
) -> tuple[PublicationId, Publication]:
    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(
        journal=journal,
        subject_area=subject_area,
        publication_type=publication_type,
        id=publication_id,
    )
    id = publication_repository.save(publication)
    return id, publication


def vocabulary_with_concepts(*concepts: str) -> Vocabulary:
    vocabulary = vocabulary_repository.create("A Vocabulary", "1.0")
    for concept in concepts:
        vocabulary.add_concept(concept)

    vocabulary_repository.save(vocabulary)
    return vocabulary
