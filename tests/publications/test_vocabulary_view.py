import pytest

from django.urls import reverse
from django.test import Client
from coda.apps.publications.models import Vocabulary as VocabularyModel

from coda.domain.vocabulary import (
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
    ConceptId,
)

from coda.apps.publications.services.vocabularies import build_concept_trees
from coda.apps.publications.views.vocabularies import annotate_trees_for_ui, UITreeNode

from coda.apps.publications.repositories import vocabulary_repository


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_limited_button__redirects_to_edit_view__has_base_vocabulary_in_context(
    client: Client,
) -> None:
    base_model = VocabularyModel.objects.create(name="Base Vocabulary", version="1.0")
    base_vocabulary_id = VocabularyId(base_model.pk)

    response = client.get(
        reverse("publications:vocabulary_create_limited", kwargs={"pk": base_vocabulary_id}),
    )

    assert response.status_code == 200
    assert "vocabulary" in response.context
    limited = response.context["vocabulary"]
    assert limited.base_vocabulary.id == base_vocabulary_id

    with pytest.raises(VocabularyModel.DoesNotExist):
        VocabularyModel.objects.get(name=limited.name)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__limited_vocabulary_with_disallowed_concept__accessing_edit_view__concept_trees_in_context(
    client: Client,
) -> None:
    vocab_id = VocabularyId(999)

    concepts, _ = create_concept_hierarchy_abc(vocab_id)
    base_vocab = create_base_vocabulary_with_concepts(vocab_id, concepts)

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

    # Test that UI trees are properly structured
    assert len(forbidden_tree) == 1
    assert forbidden_tree[0].concept.concept_id == "A"
    assert len(forbidden_tree[0].children) == 1
    assert forbidden_tree[0].children[0].concept.concept_id == "B"
    assert len(forbidden_tree[0].children[0].children) == 1
    assert forbidden_tree[0].children[0].children[0].concept.concept_id == "C"
    # Test UI annotations: C is forbidden, should show checkbox in forbidden tree
    assert forbidden_tree[0].children[0].children[0].is_allowed

    assert len(allowed_tree) == 1
    assert allowed_tree[0].concept.concept_id == "A"
    assert len(allowed_tree[0].children) == 1
    assert allowed_tree[0].children[0].concept.concept_id == "B"
    assert allowed_tree[0].children[0].children == []
    # Test UI annotations: A and B are allowed, should show checkboxes in allowed tree
    assert allowed_tree[0].is_allowed
    assert allowed_tree[0].children[0].is_allowed


@pytest.mark.django_db
def test__vocabulary_with_allowed_and_forbidden_concepts__annotating_trees_for_ui__checkboxes_are_displayed_at_the_concept() -> (
    None
):
    vocab_id = VocabularyId(997)

    id_a = ConceptId.new()
    id_b = ConceptId.new()
    concept_a = VocabularyConcept(
        id=id_a, concept_id="A", vocabulary=vocab_id, parent=None, name="A"
    )
    concept_b = VocabularyConcept(
        id=id_b, concept_id="B", vocabulary=vocab_id, parent=id_a, name="B"
    )

    base_vocab = create_base_vocabulary_with_concepts(vocab_id, [concept_a, concept_b])
    limited_vocab = create_limited_vocabulary_with_disallowed(base_vocab, ["B"], VocabularyId(996))

    (
        ui_allowed_tree,
        ui_forbidden_tree,
        max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    ) = build_and_annotate_ui_trees(limited_vocab)

    # In allowed tree: A is allowed, should show checkbox; B context not shown
    assert len(ui_allowed_tree) == 1
    assert ui_allowed_tree[0].concept.concept_id == "A"
    assert ui_allowed_tree[0].is_allowed  # A is allowed, show checkbox in allowed tree
    assert ui_allowed_tree[0].children == []  # B not shown in allowed tree

    # In forbidden tree: A is context (no checkbox), B is forbidden (checkbox)
    assert len(ui_forbidden_tree) == 1
    assert ui_forbidden_tree[0].concept.concept_id == "A"
    assert not ui_forbidden_tree[0].is_allowed  # A is allowed, no checkbox in forbidden tree
    assert len(ui_forbidden_tree[0].children) == 1
    assert ui_forbidden_tree[0].children[0].concept.concept_id == "B"
    assert (
        ui_forbidden_tree[0].children[0].is_allowed
    )  # B is forbidden, show checkbox in forbidden tree


@pytest.mark.django_db
def test__nested_hierarchial_concept_tree__building_tree__zebra_striping_indexes_assigned_sequentially() -> (
    None
):
    vocab_id = VocabularyId(995)

    concepts, _ = create_concept_hierarchy_abc(vocab_id)
    base_vocab = create_base_vocabulary_with_concepts(vocab_id, concepts)
    limited_vocab = create_limited_vocabulary_with_disallowed(base_vocab, ["C"], VocabularyId(994))

    (
        ui_allowed_tree,
        ui_forbidden_tree,
        max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    ) = build_and_annotate_ui_trees(limited_vocab)

    assert ui_allowed_tree[0].zebra_index == 1
    assert ui_allowed_tree[0].children[0].zebra_index == 2

    assert ui_forbidden_tree[0].zebra_index == 1
    assert ui_forbidden_tree[0].children[0].zebra_index == 2
    assert ui_forbidden_tree[0].children[0].children[0].zebra_index == 3


@pytest.mark.django_db
def test__vocabulary_with_structural_nodes__level_calculation__only_counts_levels_with_checkboxes() -> (
    None
):
    vocab_id = VocabularyId(998)

    concepts, _ = create_concept_hierarchy_abd(vocab_id)
    base_vocab = create_base_vocabulary_with_concepts(vocab_id, concepts)
    limited_vocab = create_limited_vocabulary_with_disallowed(base_vocab, ["B"], VocabularyId(997))

    (
        ui_allowed_tree,
        ui_forbidden_tree,
        max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    ) = build_and_annotate_ui_trees(limited_vocab)

    assert allowed_levels_with_checkboxes == {1, 3}
    assert forbidden_levels_with_checkboxes == {2}


@pytest.mark.django_db
def test__limited_vocab_from_limited_vocab__going_to_detail_view__preserves_hierarchy_with_structural_nodes() -> (
    None
):
    vocab_id = VocabularyId(995)

    concepts, _ = create_concept_hierarchy_abc(vocab_id)
    base_vocab = create_base_vocabulary_with_concepts(vocab_id, concepts)
    vocabulary_repository.save(base_vocab)

    limited1_id = VocabularyId(996)
    limited1 = LimitedVocabulary(
        id=limited1_id,
        base_vocabulary=base_vocab,
        name="Limited 1",
        version="1.0",
    )
    limited1.disallow("A")
    vocabulary_repository.save(limited1)

    limited2 = LimitedVocabulary(
        id=None,
        base_vocabulary=limited1,
        name="Limited 2",
        version="1.0",
    )

    allowed_tree, forbidden_tree, _, _, _ = build_and_annotate_ui_trees(limited2)

    root = allowed_tree[0]

    assert root.concept.concept_id == "A"
    assert root.is_allowed is False

    b_node = root.children[0]
    assert b_node.concept.concept_id == "B"
    assert b_node.is_allowed is True

    c_node = b_node.children[0]
    assert c_node.concept.concept_id == "C"
    assert c_node.is_allowed is True

    forbidden_root = forbidden_tree[0]
    assert forbidden_root.concept.concept_id == "A"
    assert forbidden_root.is_allowed is False


@pytest.mark.django_db
def test__three_level_limited_vocab_chain__build_annotated_trees__hierarchy_is_preserved() -> None:
    vocab_id = VocabularyId(993)

    concepts, _ = create_concept_hierarchy_abc(vocab_id)
    base_vocab = create_base_vocabulary_with_concepts(vocab_id, concepts)
    vocabulary_repository.save(base_vocab)

    limited1_id = VocabularyId(994)
    limited1 = LimitedVocabulary(
        id=limited1_id,
        base_vocabulary=base_vocab,
        name="Limited 1",
        version="1.0",
    )
    limited1.disallow("A")
    vocabulary_repository.save(limited1)

    limited2_id = VocabularyId(995)
    limited2 = LimitedVocabulary(
        id=limited2_id,
        base_vocabulary=limited1,
        name="Limited 2",
        version="1.0",
    )
    vocabulary_repository.save(limited2)

    limited3 = LimitedVocabulary(
        id=None,
        base_vocabulary=limited2,
        name="Limited 3",
        version="1.0",
    )

    allowed_tree, _, _, _, _ = build_and_annotate_ui_trees(limited3)

    root = allowed_tree[0]

    assert root.concept.concept_id == "A"
    assert root.is_allowed is False

    b_node = root.children[0]
    assert b_node.concept.concept_id == "B"
    assert b_node.is_allowed is True

    c_node = b_node.children[0]
    assert c_node.concept.concept_id == "C"
    assert c_node.is_allowed is True


def create_concept_hierarchy_abc(
    vocab_id: VocabularyId,
) -> tuple[list[VocabularyConcept], dict[str, ConceptId]]:
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

    concepts = [concept_a, concept_b, concept_c]
    id_mapping = {"A": id_a, "B": id_b, "C": id_c}

    return concepts, id_mapping


def create_concept_hierarchy_abd(
    vocab_id: VocabularyId,
) -> tuple[list[VocabularyConcept], dict[str, ConceptId]]:
    """Creates A -> B -> D hierarchy for testing structural nodes."""
    id_a = ConceptId.new()
    id_b = ConceptId.new()
    id_d = ConceptId.new()

    concept_a = VocabularyConcept(
        id=id_a, concept_id="A", vocabulary=vocab_id, parent=None, name="A"
    )
    concept_b = VocabularyConcept(
        id=id_b, concept_id="B", vocabulary=vocab_id, parent=id_a, name="B"
    )
    concept_d = VocabularyConcept(
        id=id_d, concept_id="D", vocabulary=vocab_id, parent=id_b, name="D"
    )

    concepts = [concept_a, concept_b, concept_d]
    id_mapping = {"A": id_a, "B": id_b, "D": id_d}

    return concepts, id_mapping


def create_base_vocabulary_with_concepts(
    vocab_id: VocabularyId, concepts: list[VocabularyConcept]
) -> Vocabulary:
    return Vocabulary(id=vocab_id, name="Test Base", version="1.0", concepts=concepts)


def create_limited_vocabulary_with_disallowed(
    base_vocab: Vocabulary, disallowed_concepts: list[str], limited_id: VocabularyId
) -> LimitedVocabulary:
    limited_vocab = LimitedVocabulary(
        id=limited_id,
        base_vocabulary=base_vocab,
        name="Limited",
        version="1.0",
    )

    for concept_id in disallowed_concepts:
        limited_vocab.disallow(concept_id)

    return limited_vocab


def build_and_annotate_ui_trees(
    limited_vocab: LimitedVocabulary,
) -> tuple[list[UITreeNode], list[UITreeNode], int, set[int], set[int]]:
    service_allowed_tree, service_forbidden_tree = build_concept_trees(limited_vocab)
    annotated = annotate_trees_for_ui(service_allowed_tree, service_forbidden_tree, limited_vocab)
    return (
        annotated.allowed_tree,
        annotated.forbidden_tree,
        annotated.max_level,
        annotated.allowed_levels_with_checkboxes,
        annotated.forbidden_levels_with_checkboxes,
    )
