from collections.abc import Collection

import pytest
from django.core.exceptions import MultipleObjectsReturned

from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.domain.publication import JournalId, PublicationId
from coda.domain.vocabulary import LimitedVocabulary, VocabularyConcept
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__saved_limited_vocabulary__get_by_id__returns_limited_vocabulary() -> None:
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept("allowed")
    v.add_concept("forbidden")
    vocabulary_repository.save(v)

    assert v.id is not None
    limited_vocabulary = vocabulary_repository.create_limited(v.id, name="limited")
    limited_vocabulary.disallow("forbidden")
    vocabulary_repository.save(limited_vocabulary)

    assert limited_vocabulary.id is not None
    actual = vocabulary_repository.get_by_id(limited_vocabulary.id)
    assert isinstance(actual, LimitedVocabulary)
    assert list(actual.concepts) == [v.get_concept("allowed")]
    assert list(actual.disallowed_concepts) == [v.get_concept("forbidden")]


@pytest.mark.django_db
def test__saved_limited_vocabulary__allowing_previously_forbidden_concept__saves_only_disallowed_concepts() -> (
    None
):
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept("allowed")
    v.add_concept("forbidden")
    vocabulary_repository.save(v)

    assert v.id is not None
    limited_vocabulary = vocabulary_repository.create_limited(v.id, name="limited")
    limited_vocabulary.disallow("forbidden")
    vocabulary_repository.save(limited_vocabulary)

    assert limited_vocabulary.id is not None
    limited_vocabulary = vocabulary_repository.get_limited_by_id(limited_vocabulary.id)
    limited_vocabulary.allow("forbidden")
    vocabulary_repository.save(limited_vocabulary)

    assert limited_vocabulary.id is not None
    result = vocabulary_repository.get_by_id(limited_vocabulary.id)
    assert sorted_by_concept_id(result.concepts) == sorted_by_concept_id(v.concepts)


@pytest.mark.django_db
def test__vocabulary_in_use_by_publication__delete__raises_error() -> None:
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept("concept")
    vocabulary_repository.save(v)

    concept = v.get_concept("concept")
    create_publication_with_publication_type(concept)

    with pytest.raises(vocabulary_repository.VocabularyInUseError):
        vocabulary_repository.delete(v)

    assert v.id is not None
    assert vocabulary_repository.get_by_id(v.id) is not None


@pytest.mark.django_db
def test__vocabulary_with_limited_vocabulary__delete__raises_error() -> None:
    v = vocabulary_repository.create(name="test", version="1.0")
    v.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(v)

    assert v.id is not None
    _ = vocabulary_repository.create_limited(v.id, "limited")

    with pytest.raises(vocabulary_repository.VocabularyInUseError):
        vocabulary_repository.delete(v)

    assert v.id is not None
    assert vocabulary_repository.get_by_id(v.id) is not None


@pytest.mark.django_db
def test__limited_vocab_based_on_limited_vocab__loading_from_db__preserves_correct_vocabulary_and_concepts_chain() -> (
    None
):
    base = vocabulary_repository.create(name="Base", version="1.0")
    base.add_concept("A")
    base.add_concept("B")
    base.add_concept("C")
    vocabulary_repository.save(base)

    assert base.id is not None
    limited1 = vocabulary_repository.create_limited(base.id, name="Limited 1")
    limited1.disallow("A")
    vocabulary_repository.save(limited1)

    assert limited1.id is not None
    limited2 = vocabulary_repository.create_limited(limited1.id, name="Limited 2")
    vocabulary_repository.save(limited2)

    assert limited2.id is not None
    loaded_limited2 = vocabulary_repository.get_limited_by_id(limited2.id)

    assert loaded_limited2.base_vocabulary.id == limited1.id

    base_concepts = {c.concept_id for c in loaded_limited2.base_vocabulary.concepts}
    assert base_concepts == {"B", "C"}

    limited2_concepts = {c.concept_id for c in loaded_limited2.concepts}
    assert limited2_concepts == {"B", "C"}


def sorted_by_concept_id(concepts: Collection[VocabularyConcept]) -> list[VocabularyConcept]:
    return sorted(concepts, key=lambda c: c.concept_id)


# --- Fix M5: first_by_name → get_by_name naming vs. behaviour mismatch ---


@pytest.mark.django_db
def test__vocabulary_repository__get_by_name__returns_matching_vocabulary() -> None:
    """get_by_name must return the vocabulary with the given name (happy path)."""
    v = vocabulary_repository.create(name="my-vocabulary", version="1.0")
    vocabulary_repository.save(v)

    result = vocabulary_repository.get_by_name("my-vocabulary")

    assert result.name == "my-vocabulary"


@pytest.mark.django_db
def test__vocabulary_repository__get_by_name__nonexistent_name__raises_not_found() -> None:
    """get_by_name must raise VocabularyNotFoundError for an unknown name."""
    with pytest.raises(vocabulary_repository.VocabularyNotFoundError):
        vocabulary_repository.get_by_name("does-not-exist")


@pytest.mark.django_db
def test__vocabulary_repository__get_by_name__multiple_matches__raises_error() -> None:
    """get_by_name must raise when multiple vocabularies share the same name.

    There is no DB unique constraint on name, so duplicates can exist.
    The method semantics are 'get the single vocabulary with this name'; if
    there are multiple matches it must signal an error rather than silently
    returning an arbitrary one.
    """
    v1 = vocabulary_repository.create(name="duplicate", version="1.0")
    vocabulary_repository.save(v1)
    v2 = vocabulary_repository.create(name="duplicate", version="2.0")
    vocabulary_repository.save(v2)

    with pytest.raises(MultipleObjectsReturned):
        vocabulary_repository.get_by_name("duplicate")


def create_publication_with_publication_type(concept: VocabularyConcept) -> PublicationId:
    journal = JournalId(modelfactory.journal().pk)
    p = domainfactory.publication(journal, publication_type=concept)
    return publication_repository.create(p)


def create_publication_with_subject_area(concept: VocabularyConcept) -> PublicationId:
    journal = JournalId(modelfactory.journal().pk)
    p = domainfactory.publication(journal, subject_area=concept)
    return publication_repository.create(p)
