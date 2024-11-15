import pytest

from coda.vocabulary import (
    ConceptId,
    DuplicateConceptError,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
)


def test__can_create_vocabulary_with_concepts() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    sut.add_concept(id=ConceptId("test-concept"), name="Test Concept", description="A test concept")
    sut.add_concept(
        id=ConceptId("test-concept-2"), name="Test Concept", description="A test concept"
    )

    assert list(sut.concepts) == [
        VocabularyConcept(
            id=ConceptId("test-concept"),
            name="Test Concept",
            description="A test concept",
            vocabulary=VocabularyId(0),
        ),
        VocabularyConcept(
            id=ConceptId("test-concept-2"),
            name="Test Concept",
            description="A test concept",
            vocabulary=VocabularyId(0),
        ),
    ]


def test__concept_ids__must_be_unique() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    sut.add_concept(id=ConceptId("test-concept"), name="Test Concept", description="A test concept")

    with pytest.raises(DuplicateConceptError):
        sut.add_concept(
            id=ConceptId("test-concept"), name="Test Concept", description="A test concept"
        )


def test__vocabulary__all_concepts_are_allowed_by_default() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    sut.add_concept(id=ConceptId("test-concept"), name="", description="")
    sut.add_concept(id=ConceptId("test-concept-2"), name="", description="")

    assert all(c.is_allowed for c in sut.concepts)
    assert sut.is_allowed(ConceptId("test-concept"))
    assert list(sut.allowed_concepts()) == list(sut.concepts)


def test__set_concept_forbidden__is_not_allowed() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    sut.add_concept(id=ConceptId("test-concept"), name="", description="")

    sut.set_forbidden(ConceptId("test-concept"))

    concept = sut.get_concept(ConceptId("test-concept"))
    assert concept.is_allowed is False
    assert concept not in sut.allowed_concepts()


def test__forbidden_concept__set_allowed__is_in_vocabulary_allowed_concepts() -> None:
    sut = Vocabulary(id=VocabularyId(0), name="test", version="1.0")
    initially_not_allowed = ConceptId("test-concept")
    allowed = ConceptId("test-concept-2")
    sut.add_concept(id=initially_not_allowed, name="", description="", is_allowed=False)
    sut.add_concept(id=allowed, name="", description="")

    sut.set_allowed(initially_not_allowed)

    expected = {sut.get_concept(allowed), sut.get_concept(initially_not_allowed)}
    assert set(sut.allowed_concepts()) == expected


def test__two_concepts_with_same_concept_id_and_vocabulary_id__are_always_equal() -> None:
    cid = ConceptId("test-concept")
    vid = VocabularyId(0)
    concept = VocabularyConcept(id=cid, vocabulary=vid)
    same_concept_with_more_data = VocabularyConcept(id=cid, vocabulary=vid, name="Additional Info")

    assert concept == same_concept_with_more_data


def test__two_concepts_with_different_vocabulary_ids__are_not_equal() -> None:
    cid = ConceptId("test-concept")
    vid = VocabularyId(0)
    concept = VocabularyConcept(id=cid, vocabulary=vid)

    other_vid = VocabularyId(1)
    other_vocabulary_same_concept = VocabularyConcept(id=cid, vocabulary=other_vid)

    assert concept != other_vocabulary_same_concept


def test__two_concepts_with_different_concept_ids__are_not_equal() -> None:
    cid = ConceptId("test-concept")
    vid = VocabularyId(0)
    concept = VocabularyConcept(id=cid, vocabulary=vid)

    other_cid = ConceptId("other-concept")
    other_concept_same_vocabulary = VocabularyConcept(id=other_cid, vocabulary=vid)

    assert concept != other_concept_same_vocabulary
