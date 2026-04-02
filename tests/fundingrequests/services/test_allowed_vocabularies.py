from collections.abc import Callable
from typing import Literal, NamedTuple, cast

import pytest

from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.repositories import vocabulary_repository
from coda.contexts.fundingrequest.services.allowed_vocabularies import (
    AllowedConcepts,
    InvalidPublicationType,
    InvalidSubjectType,
)
from coda.domain.contract import PublisherId
from coda.domain.publication.publication import BasePublication, JournalId
from coda.domain.vocabulary import UnknownConcept, Vocabulary
from tests import domainfactory, modelfactory

PublicationFactory = Callable[[], BasePublication]
VocabularySetter = Callable[[Vocabulary], None]


class PublicationTypeKind(NamedTuple):
    kind: Literal["article", "monograph"]
    set_vocabulary: VocabularySetter
    create_publication: PublicationFactory


@pytest.fixture(
    params=[
        PublicationTypeKind(
            kind="article",
            set_vocabulary=GlobalPreferences.set_article_publication_type_vocabulary,
            create_publication=lambda: domainfactory.publication(
                JournalId(modelfactory.journal().pk)
            ),
        ),
        PublicationTypeKind(
            kind="monograph",
            set_vocabulary=GlobalPreferences.set_monograph_publication_type_vocabulary,
            create_publication=lambda: domainfactory.monograph(
                PublisherId(modelfactory.publisher().pk)
            ),
        ),
    ]
)
def publication_type_kind(request: pytest.FixtureRequest) -> PublicationTypeKind:
    return cast(PublicationTypeKind, request.param)


@pytest.fixture(
    params=[
        lambda: domainfactory.publication(JournalId(modelfactory.journal().pk)),
        lambda: domainfactory.monograph(PublisherId(modelfactory.publisher().pk)),
    ]
)
def any_publication(request: pytest.FixtureRequest) -> PublicationFactory:
    return cast(PublicationFactory, request.param)


# ---------------------------------------------------------------------------
# for_new_publication — no grandfather clause, only current vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test__for_new_publication__returns_allowed_publication_types(
    publication_type_kind: PublicationTypeKind,
) -> None:
    vocabulary = vocabulary_with_concepts(
        "my vocabulary", concepts=["a_concept", "another_concept"]
    )
    publication_type_kind.set_vocabulary(vocabulary)

    allowed = AllowedConcepts.for_new_publication(publication_type_kind.kind)

    assert ["a_concept", "another_concept"] == [c.concept_id for c in allowed.publication_types]


@pytest.mark.django_db
def test__for_new_publication__returns_allowed_subject_types() -> None:
    vocabulary = vocabulary_with_concepts("subject vocabulary", concepts=["subject_a", "subject_b"])
    GlobalPreferences.set_subject_classification_vocabulary(vocabulary)

    allowed = AllowedConcepts.for_new_publication("article")

    assert ["subject_a", "subject_b"] == [c.concept_id for c in allowed.subject_types]


# ---------------------------------------------------------------------------
# for_existing_publication — grandfather clause: existing concepts always allowed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test__for_existing_publication__existing_publication_type_included_after_vocabulary_switch(
    publication_type_kind: PublicationTypeKind,
) -> None:
    old = vocabulary_with_concepts(
        "old vocabulary", concepts=["old_concept", "not_allowed_old_concept"]
    )
    new = vocabulary_with_concepts("new vocabulary", concepts=["new_concept"])
    publication_type_kind.set_vocabulary(new)

    publication = publication_type_kind.create_publication()
    publication.publication_type = old.get_concept("old_concept")

    allowed = AllowedConcepts.for_existing_publication(publication)

    assert ["old_concept", "new_concept"] == [c.concept_id for c in allowed.publication_types]


@pytest.mark.django_db
def test__for_existing_publication__existing_type_already_in_new_vocabulary_is_not_duplicated(
    publication_type_kind: PublicationTypeKind,
) -> None:
    vocabulary = vocabulary_with_concepts(
        "vocabulary", concepts=["shared_concept", "other_concept"]
    )
    publication_type_kind.set_vocabulary(vocabulary)

    publication = publication_type_kind.create_publication()
    publication.publication_type = vocabulary.get_concept("shared_concept")

    allowed = AllowedConcepts.for_existing_publication(publication)

    assert ["shared_concept", "other_concept"] == [c.concept_id for c in allowed.publication_types]


@pytest.mark.django_db
def test__for_existing_publication__existing_subject_included_after_vocabulary_switch(
    any_publication: PublicationFactory,
) -> None:
    old = vocabulary_with_concepts(
        "old subject vocabulary", concepts=["old_subject", "not_allowed_old_subject"]
    )
    new = vocabulary_with_concepts("new subject vocabulary", concepts=["new_subject"])
    GlobalPreferences.set_subject_classification_vocabulary(new)

    publication = any_publication()
    publication.subject_area = old.get_concept("old_subject")

    allowed = AllowedConcepts.for_existing_publication(publication)

    assert ["old_subject", "new_subject"] == [c.concept_id for c in allowed.subject_types]


@pytest.mark.django_db
def test__for_existing_publication__existing_subject_already_in_new_vocabulary_is_not_duplicated(
    any_publication: PublicationFactory,
) -> None:
    vocabulary = vocabulary_with_concepts(
        "subject vocabulary", concepts=["shared_subject", "other_subject"]
    )
    GlobalPreferences.set_subject_classification_vocabulary(vocabulary)

    publication = any_publication()
    publication.subject_area = vocabulary.get_concept("shared_subject")

    allowed = AllowedConcepts.for_existing_publication(publication)

    assert ["shared_subject", "other_subject"] == [c.concept_id for c in allowed.subject_types]


# ---------------------------------------------------------------------------
# validate — raises on disallowed concepts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test__validate__allowed_publication_type__does_not_raise(
    publication_type_kind: PublicationTypeKind,
) -> None:
    vocabulary = vocabulary_with_concepts(
        "vocabulary", concepts=["allowed_concept", "other_concept"]
    )
    publication_type_kind.set_vocabulary(vocabulary)
    GlobalPreferences.set_subject_classification_vocabulary(vocabulary)

    publication = publication_type_kind.create_publication()
    allowed = AllowedConcepts.for_existing_publication(publication)

    allowed.validate(
        vocabulary.get_concept("allowed_concept"), vocabulary.get_concept("other_concept")
    )


@pytest.mark.django_db
def test__validate__disallowed_publication_type__raises_invalid_publication_type(
    publication_type_kind: PublicationTypeKind,
) -> None:
    allowed_vocab = vocabulary_with_concepts("allowed vocabulary", concepts=["allowed_concept"])
    disallowed_vocab = vocabulary_with_concepts("other vocabulary", concepts=["disallowed_concept"])
    publication_type_kind.set_vocabulary(allowed_vocab)
    GlobalPreferences.set_subject_classification_vocabulary(allowed_vocab)

    publication = publication_type_kind.create_publication()
    allowed = AllowedConcepts.for_existing_publication(publication)

    with pytest.raises(InvalidPublicationType):
        allowed.validate(
            disallowed_vocab.get_concept("disallowed_concept"),
            allowed_vocab.get_concept("allowed_concept"),
        )


@pytest.mark.django_db
def test__validate__disallowed_subject_area__raises_invalid_subject_type(
    any_publication: PublicationFactory,
) -> None:
    allowed_vocab = vocabulary_with_concepts("allowed vocabulary", concepts=["allowed_subject"])
    disallowed_vocab = vocabulary_with_concepts("other vocabulary", concepts=["disallowed_subject"])
    GlobalPreferences.set_subject_classification_vocabulary(allowed_vocab)

    publication = any_publication()
    allowed = AllowedConcepts.for_existing_publication(publication)

    with pytest.raises(InvalidSubjectType):
        allowed.validate(UnknownConcept, disallowed_vocab.get_concept("disallowed_subject"))


@pytest.mark.django_db
def test__validate__existing_publication_type_allowed_after_vocabulary_switch(
    publication_type_kind: PublicationTypeKind,
) -> None:
    old = vocabulary_with_concepts("old vocabulary", concepts=["old_concept"])
    new = vocabulary_with_concepts("new vocabulary", concepts=["new_concept"])
    publication_type_kind.set_vocabulary(new)
    GlobalPreferences.set_subject_classification_vocabulary(new)

    publication = publication_type_kind.create_publication()
    publication.publication_type = old.get_concept("old_concept")

    allowed = AllowedConcepts.for_existing_publication(publication)

    # The old concept should still be allowed due to the grandfather clause
    allowed.validate(old.get_concept("old_concept"), new.get_concept("new_concept"))


# ---------------------------------------------------------------------------
# UnknownConcept is always allowed (it is the "no selection" sentinel)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test__validate__unknown_publication_type__always_allowed(
    publication_type_kind: PublicationTypeKind,
) -> None:
    vocabulary = vocabulary_with_concepts("vocab", concepts=["some-type"])
    publication_type_kind.set_vocabulary(vocabulary)
    GlobalPreferences.set_subject_classification_vocabulary(vocabulary)

    publication = publication_type_kind.create_publication()
    allowed = AllowedConcepts.for_existing_publication(publication)

    # UnknownConcept is always valid — no exception raised
    allowed.validate(UnknownConcept, vocabulary.get_concept("some-type"))


@pytest.mark.django_db
def test__validate__unknown_subject_area__always_allowed(
    any_publication: PublicationFactory,
) -> None:
    subject_vocab = vocabulary_with_concepts("vocab", concepts=["some-subject"])
    pub_type_vocab = vocabulary_with_concepts("pub-type vocab", concepts=["some-type"])
    GlobalPreferences.set_subject_classification_vocabulary(subject_vocab)
    GlobalPreferences.set_article_publication_type_vocabulary(pub_type_vocab)
    GlobalPreferences.set_monograph_publication_type_vocabulary(pub_type_vocab)

    publication = any_publication()
    allowed = AllowedConcepts.for_existing_publication(publication)

    # UnknownConcept is always valid as subject_area — no exception raised
    allowed.validate(pub_type_vocab.get_concept("some-type"), UnknownConcept)


# ---------------------------------------------------------------------------
# for_existing_concepts — grandfather via explicit concept values (DTO path)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test__for_existing_concepts__grandfathers_supplied_concepts(
    publication_type_kind: PublicationTypeKind,
) -> None:
    old = vocabulary_with_concepts("old vocabulary", concepts=["old_concept"])
    new = vocabulary_with_concepts("new vocabulary", concepts=["new_concept"])
    subject_vocab = vocabulary_with_concepts("subjects", concepts=["subject_a"])
    publication_type_kind.set_vocabulary(new)
    GlobalPreferences.set_subject_classification_vocabulary(subject_vocab)

    allowed = AllowedConcepts.for_existing_concepts(
        publication_type_kind.kind,
        publication_type=old.get_concept("old_concept"),
        subject_area=subject_vocab.get_concept("subject_a"),
    )

    assert "old_concept" in [c.concept_id for c in allowed.publication_types]
    assert "new_concept" in [c.concept_id for c in allowed.publication_types]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def vocabulary_with_concepts(name: str, *, concepts: list[str]) -> Vocabulary:
    v = vocabulary_repository.create(name, "1.0")
    for c in concepts:
        v.add_concept(c)

    vocabulary_repository.save(v)
    return v
