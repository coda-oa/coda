import pytest

from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
)


@pytest.mark.django_db
def test__limited_vocabulary_with_disallowed_concept__building_hierarchy__returns_correct_structure_and_allows_status_check() -> (
    None
):
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

    # Test hierarchy access
    roots, children_map = limited_vocabulary.get_concept_hierarchy()

    assert len(roots) == 1
    assert roots[0].concept_id == "A"
    assert parent_concept_id in children_map
    assert len(children_map[parent_concept_id]) == 1
    assert children_map[parent_concept_id][0].concept_id == "B"

    # Test concept status checking
    assert limited_vocabulary.is_concept_allowed("A")
    assert not limited_vocabulary.is_concept_allowed("B")


@pytest.mark.django_db
def test__limited_vocabulary_with_multilevel_hierarchy_and_disallowed_concept__building_hierarchy__returns_correct_tree_and_status() -> (
    None
):
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

    # Test hierarchy structure
    roots, children_map = limited_vocabulary.get_concept_hierarchy()

    assert len(roots) == 1
    assert roots[0].concept_id == "A"

    # Test A → B relationship
    assert grandparent_concept_id in children_map
    assert len(children_map[grandparent_concept_id]) == 1
    assert children_map[grandparent_concept_id][0].concept_id == "B"

    # Test B → C relationship
    assert parent_concept_id in children_map
    assert len(children_map[parent_concept_id]) == 1
    assert children_map[parent_concept_id][0].concept_id == "C"

    # Test concept allowance status
    assert limited_vocabulary.is_concept_allowed("A")
    assert limited_vocabulary.is_concept_allowed("B")
    assert not limited_vocabulary.is_concept_allowed("C")
