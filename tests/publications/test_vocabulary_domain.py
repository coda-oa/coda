import pytest

from django.urls import reverse
from django.test import Client

from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
)

from coda.apps.publications.repositories import vocabulary_repository


@pytest.mark.django_db
def test__limited_vocabulary_with_hierarchial_concepts__returns_expected_tree_nodes() -> None:
    parent_concept_id = ConceptId.new()
    child_concept_id = ConceptId.new()

    parent_concept = VocabularyConcept(
        id=parent_concept_id, concept_id="A", vocabulary=VocabularyId(1), name="Parent", parent=None
    )
    child_concept = VocabularyConcept(
        id=child_concept_id,
        concept_id="B",
        vocabulary=VocabularyId(1),
        name="Child",
        parent=parent_concept_id,
    )

    base_vocabulary = Vocabulary(
        id=VocabularyId(1), name="Base", version="1.0", concepts=[parent_concept, child_concept]
    )

    limited_vocabulary = LimitedVocabulary(
        id=VocabularyId(2),
        base_vocabulary=base_vocabulary,
        name="Limited",
        version="1.0",
    )

    limited_vocabulary.disallow("B")

    _, forbidden_concepts_tree = limited_vocabulary.get_concept_trees()

    assert len(forbidden_concepts_tree) == 1
    assert forbidden_concepts_tree[0].concept.concept_id == "A"
    assert len(forbidden_concepts_tree[0].children) == 1
    assert forbidden_concepts_tree[0].children[0].concept.concept_id == "B"


@pytest.mark.django_db
def test__limited_vocabulary_with_multilevel_hierarchy__returns_expected_tree_nodes() -> None:
    grandparent_concept_id = ConceptId.new()
    parent_concept_id = ConceptId.new()
    child_concept_id = ConceptId.new()

    grandparent_concept = VocabularyConcept(
        id=grandparent_concept_id,
        concept_id="A",
        vocabulary=VocabularyId(1),
        name="Grandparent",
        parent=None,
    )
    parent_concept = VocabularyConcept(
        id=parent_concept_id,
        concept_id="B",
        vocabulary=VocabularyId(1),
        name="Parent",
        parent=grandparent_concept_id,
    )
    child_concept = VocabularyConcept(
        id=child_concept_id,
        concept_id="C",
        vocabulary=VocabularyId(1),
        name="Child",
        parent=parent_concept_id,
    )

    base_vocabulary = Vocabulary(
        id=VocabularyId(1),
        name="Base",
        version="1.0",
        concepts=[grandparent_concept, parent_concept, child_concept],
    )

    limited_vocabulary = LimitedVocabulary(
        id=VocabularyId(2),
        base_vocabulary=base_vocabulary,
        name="Limited",
        version="1.0",
    )

    limited_vocabulary.disallow("C")

    allowed_concepts_tree, forbidden_concepts_tree = limited_vocabulary.get_concept_trees()

    assert len(allowed_concepts_tree) == 1
    assert allowed_concepts_tree[0].concept.concept_id == "A"
    assert len(allowed_concepts_tree[0].children) == 1
    assert allowed_concepts_tree[0].children[0].concept.concept_id == "B"
    assert allowed_concepts_tree[0].children[0].children == []

    assert len(forbidden_concepts_tree) == 1
    assert forbidden_concepts_tree[0].concept.concept_id == "A"
    assert len(forbidden_concepts_tree[0].children) == 1
    assert forbidden_concepts_tree[0].children[0].concept.concept_id == "B"
    assert len(forbidden_concepts_tree[0].children[0].children) == 1
    assert forbidden_concepts_tree[0].children[0].children[0].concept.concept_id == "C"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__edit_limited_view__has__concept_trees_in_context(client: Client) -> None:
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

    vocabulary_repository.save(base_vocab)

    limited_vocab = vocabulary_repository.create_limited(
        base_vocabulary_id=vocab_id, name="Limited"
    )

    limited_vocab.disallow("C")

    vocabulary_repository.save(limited_vocab)

    url = reverse("publications:vocabulary_edit_limited", kwargs={"pk": limited_vocab.id})
    response = client.get(url)

    assert response.status_code == 200
    assert "allowed_tree" in response.context
    assert "forbidden_tree" in response.context

    allowed_tree = response.context["allowed_tree"]
    forbidden_tree = response.context["forbidden_tree"]

    assert len(forbidden_tree) == 1
    assert forbidden_tree[0].concept.concept_id == "A"
    assert len(forbidden_tree[0].children) == 1
    assert forbidden_tree[0].children[0].concept.concept_id == "B"
    assert len(forbidden_tree[0].children[0].children) == 1
    assert forbidden_tree[0].children[0].children[0].concept.concept_id == "C"

    assert len(allowed_tree) == 1
    assert allowed_tree[0].concept.concept_id == "A"
    assert len(allowed_tree[0].children) == 1
    assert allowed_tree[0].children[0].concept.concept_id == "B"
    assert allowed_tree[0].children[0].children == []


@pytest.mark.django_db
def test__tree_node_is_allowed_field_set_correctly() -> None:
    """Test that TreeNode.is_allowed is set correctly for template checkbox display"""
    # Create test vocabulary with A → B → C hierarchy
    vocab_id = VocabularyId(997)

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
    # Disallow only C
    limited_vocab.disallow("C")

    allowed_tree, forbidden_tree = limited_vocab.get_concept_trees()

    # In allowed tree: A should show checkbox (is_allowed=True), B should show checkbox (is_allowed=True)
    assert len(allowed_tree) == 1
    assert allowed_tree[0].concept.concept_id == "A"
    assert allowed_tree[0].is_allowed  # A is allowed, should show checkbox in allowed tree
    assert len(allowed_tree[0].children) == 1
    assert allowed_tree[0].children[0].concept.concept_id == "B"
    assert (
        allowed_tree[0].children[0].is_allowed
    )  # B is allowed, should show checkbox in allowed tree

    # In forbidden tree: A should NOT show checkbox (is_allowed=False), B should NOT show checkbox, C should show checkbox
    assert len(forbidden_tree) == 1
    assert forbidden_tree[0].concept.concept_id == "A"
    assert not forbidden_tree[
        0
    ].is_allowed  # A is allowed, should NOT show checkbox in forbidden tree
    assert len(forbidden_tree[0].children) == 1
    assert forbidden_tree[0].children[0].concept.concept_id == "B"
    assert (
        not forbidden_tree[0].children[0].is_allowed
    )  # B is allowed, should NOT show checkbox in forbidden tree
    assert len(forbidden_tree[0].children[0].children) == 1
    assert forbidden_tree[0].children[0].children[0].concept.concept_id == "C"
    assert (
        forbidden_tree[0].children[0].children[0].is_allowed
    )  # C is forbidden, should show checkbox in forbidden tree
