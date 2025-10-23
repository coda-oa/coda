from collections.abc import Callable

import pytest

from coda.apps.publications.repositories import publication_repository, vocabulary_repository
from coda.apps.publications.services import vocabularies
from coda.apps.publications.services.vocabularies import build_concept_trees
from coda.domain.publication import BasePublication, PublicationId
from coda.domain.vocabulary import (
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
    ConceptId,
)
from tests.publications.test_vocabulary_repository import (
    create_publication_with_publication_type,
    create_publication_with_subject_area,
)


@pytest.mark.django_db
def test__can_create_limited_vocabulary_from_vocabulary() -> None:
    vocabulary = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)

    assert vocabulary.id is not None  # Should have ID after save
    vid = vocabularies.create_limited_from(vocabulary.id, "limited")

    actual = vocabulary_repository.get_by_id(vid)
    assert isinstance(actual, LimitedVocabulary)
    assert actual.name == "limited"
    assert vocabulary.id is not None  # Type assertion
    assert actual.base_vocabulary.id == vocabulary.id
    assert actual.version == actual.base_vocabulary.version


@pytest.mark.django_db
def test__limited_vocabulary__disallowing_concept__is_saved_to_database() -> None:
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)

    assert vocabulary.id is not None  # Repository create should assign ID
    vid = vocabularies.create_limited_from(vocabulary.id, "limited")

    vocabularies.disallow_concept(vid, "test-concept")

    actual = vocabulary_repository.get_limited_by_id(vid)
    assert list(actual.disallowed_concepts) == [vocabulary.get_concept("test-concept")]


@pytest.mark.django_db
def test__limited_vocabulary_with_disallowed_concepts__allowing_concept__is_saved_to_database() -> (
    None
):
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)

    assert vocabulary.id is not None  # Repository create should assign ID
    vid = vocabularies.create_limited_from(vocabulary.id, "limited")
    vocabularies.disallow_concept(vid, "test-concept")

    vocabularies.allow_concept(vid, "test-concept")

    actual = vocabulary_repository.get_limited_by_id(vid)
    assert list(actual.disallowed_concepts) == []


PublicationWithConceptFactory = Callable[[VocabularyConcept], PublicationId]
PublicationVocabularyAccessor = Callable[[BasePublication], VocabularyId]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("publication_factory", "get_vocabulary"),
    (
        (create_publication_with_publication_type, lambda p: p.publication_type.vocabulary),
        (create_publication_with_subject_area, lambda p: p.subject_area.vocabulary),
    ),
)
def test__given_publication_using_limited_vocabulary__delete_vocabulary__migrates_publications_to_base_vocabulary(
    publication_factory: PublicationWithConceptFactory,
    get_vocabulary: PublicationVocabularyAccessor,
) -> None:
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)

    assert vocabulary.id is not None  # Repository create should assign ID
    limited = vocabulary_repository.create_limited(vocabulary.id, "limited")

    concept = limited.get_concept("test-concept")
    publication_id = publication_factory(concept)

    assert limited.id is not None  # Repository create_limited should assign ID
    vocabularies.delete(limited.id)

    publication = publication_repository.get_by_id(publication_id)
    actual_vocabulary = get_vocabulary(publication)

    assert actual_vocabulary == vocabulary.id
    with pytest.raises(vocabulary_repository.VocabularyNotFoundError):
        assert limited.id is not None  # Type assertion for mypy
        vocabulary_repository.get_by_id(limited.id)


@pytest.mark.django_db
def test__given_limited_vocabulary_used_by_publication__usage_report__contains_publication_and_base_vocabulary() -> (
    None
):
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)
    assert vocabulary.id is not None  # Repository create should assign ID
    limited = vocabulary_repository.create_limited(vocabulary.id, "limited")

    concept = vocabulary.get_concept("test-concept")
    publication_id = create_publication_with_publication_type(concept)

    assert vocabulary.id is not None  # Type assertion for mypy
    actual = vocabularies.get_usage(vocabulary.id)

    assert actual.vocabulary == vocabulary
    assert actual.publications == [publication_repository.get_by_id(publication_id)]
    assert actual.derived_vocabularies == [limited]


@pytest.mark.django_db
def test__vocabulary_usage__with_no_publications_or_derived_vocabularies__can_be_deleted() -> None:
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)

    assert vocabulary.id is not None  # Repository create should assign ID
    actual = vocabularies.get_usage(vocabulary.id)

    assert actual.can_be_deleted() is True


@pytest.mark.django_db
def test__vocabulary_usage_of_base_vocabulary__with_derived_vocabularies__cannot_be_deleted() -> (
    None
):
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)
    assert vocabulary.id is not None  # Repository create should assign ID
    _ = vocabulary_repository.create_limited(vocabulary.id, "limited")

    assert vocabulary.id is not None  # Type assertion for mypy
    actual = vocabularies.get_usage(vocabulary.id)

    assert actual.can_be_deleted() is False


@pytest.mark.django_db
def test__vocabulary_usage_of_vocabulary__with_publications__cannot_be_deleted() -> None:
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)

    concept = vocabulary.get_concept("test-concept")
    _ = create_publication_with_publication_type(concept)

    assert vocabulary.id is not None  # Repository create should assign ID
    actual = vocabularies.get_usage(vocabulary.id)

    assert actual.can_be_deleted() is False


@pytest.mark.django_db
def test__vocabulary_usage_of_limited_vocabulary__with_publications__can_be_deleted() -> None:
    vocabulary = vocabulary_repository.create(name="test", version="1.0")
    vocabulary.add_concept(concept_id="test-concept", name="", description="")
    vocabulary_repository.save(vocabulary)
    assert vocabulary.id is not None  # Repository create should assign ID
    limited = vocabulary_repository.create_limited(vocabulary.id, "limited")

    concept = limited.get_concept("test-concept")
    _ = create_publication_with_publication_type(concept)

    assert limited.id is not None  # Repository create_limited should assign ID
    actual = vocabularies.get_usage(limited.id)

    assert actual.can_be_deleted() is True


@pytest.mark.django_db
def test__vocabulary_with_hierarchical_concepts__building_concept_trees__allowed_and_forbidden_concept_trees_with_hierarchy() -> (
    None
):
    vocab_id = VocabularyId(999)

    id_a = ConceptId.new()
    id_b = ConceptId.new()
    id_c = ConceptId.new()

    concept_a = VocabularyConcept(
        id=id_a, concept_id="A", vocabulary=vocab_id, parent=None, name="A"
    )
    concept_b = VocabularyConcept(
        id=id_b, concept_id="B", vocabulary=vocab_id, parent=id_a, name="B"
    )
    concept_c = VocabularyConcept(
        id=id_c, concept_id="C", vocabulary=vocab_id, parent=id_b, name="C"
    )

    base_vocab = Vocabulary(
        id=vocab_id, name="Test Base", version="1.0", concepts=[concept_a, concept_b, concept_c]
    )

    limited_vocab = LimitedVocabulary(
        id=VocabularyId(998),
        base_vocabulary=base_vocab,
        name="Limited",
        version="1.0",
    )

    limited_vocab.disallow("C")

    allowed_tree, forbidden_tree = build_concept_trees(limited_vocab)

    # Test allowed tree structure (A and B are allowed)
    assert len(allowed_tree) == 1
    assert allowed_tree[0].concept.concept_id == "A"
    assert len(allowed_tree[0].children) == 1
    assert allowed_tree[0].children[0].concept.concept_id == "B"
    assert allowed_tree[0].children[0].children == []  # C is not in allowed tree

    # Test forbidden tree structure (includes context: A → B → C)
    assert len(forbidden_tree) == 1
    assert forbidden_tree[0].concept.concept_id == "A"
    assert len(forbidden_tree[0].children) == 1
    assert forbidden_tree[0].children[0].concept.concept_id == "B"
    assert len(forbidden_tree[0].children[0].children) == 1
    assert forbidden_tree[0].children[0].children[0].concept.concept_id == "C"
