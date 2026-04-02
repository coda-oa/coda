from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from coda.apps.preferences.models import GlobalPreferences
from coda.domain.errors import DomainError
from coda.domain.publication.publication import BasePublication
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept, VocabularyProtocol


class InvalidPublicationType(DomainError):
    pass


class InvalidSubjectType(DomainError):
    pass


def _get_concepts_from_vocabulary(
    vocabulary: VocabularyProtocol, allow_extra: VocabularyConcept | None = None
) -> Collection[VocabularyConcept]:
    if allow_extra is None:
        return vocabulary.concepts
    return [allow_extra, *(c for c in vocabulary.concepts if c != allow_extra)]


def _is_concept_allowed(concept: VocabularyConcept, allowed: Collection[VocabularyConcept]) -> bool:
    if concept == UnknownConcept:
        return True
    return concept in allowed


def _get_publication_types_for_kind(
    kind: Literal["article", "monograph"],
    allow_extra: VocabularyConcept | None = None,
) -> Collection[VocabularyConcept]:
    if kind == "article":
        vocabulary = GlobalPreferences.get_article_publication_type_vocabulary()
    else:
        vocabulary = GlobalPreferences.get_monograph_publication_type_vocabulary()
    return _get_concepts_from_vocabulary(vocabulary, allow_extra)


def _get_subject_types(
    allow_extra: VocabularyConcept | None = None,
) -> Collection[VocabularyConcept]:
    vocabulary = GlobalPreferences.get_subject_classification_vocabulary()
    return _get_concepts_from_vocabulary(vocabulary, allow_extra)


@dataclass(frozen=True)
class AllowedConcepts:
    """Encapsulates the allowed vocabulary concepts for a publication.

    The grandfathering policy — allowing an existing concept even if it has
    since been removed from the active vocabulary — is encoded at construction
    time via the named factory methods, not scattered across call sites.

    Use ``for_new_publication`` when no concept has been persisted yet
    (strict: only the current vocabulary is valid).

    Use ``for_existing_publication`` when the publication already owns
    concepts that must remain selectable even after a vocabulary switch
    (grandfather clause).
    """

    publication_types: Collection[VocabularyConcept]
    subject_types: Collection[VocabularyConcept]

    @classmethod
    def for_new_publication(cls, kind: Literal["article", "monograph"]) -> "AllowedConcepts":
        """No grandfather clause — only the current vocabulary is valid."""
        return cls(
            publication_types=_get_publication_types_for_kind(kind),
            subject_types=_get_subject_types(),
        )

    @classmethod
    def for_existing_publication(cls, publication: BasePublication) -> "AllowedConcepts":
        """Grandfather clause: the publication's current concepts are always allowed,
        even if they have since been removed from the active vocabulary."""
        return cls(
            publication_types=_get_publication_types_for_kind(
                publication.kind, allow_extra=publication.publication_type
            ),
            subject_types=_get_subject_types(allow_extra=publication.subject_area),
        )

    @classmethod
    def for_existing_concepts(
        cls,
        kind: Literal["article", "monograph"],
        publication_type: VocabularyConcept,
        subject_area: VocabularyConcept,
    ) -> "AllowedConcepts":
        """Grandfather clause for when the domain object is not available.

        Use this when you only have the publication kind and the current concept
        values (e.g. when building a form from a DTO rather than a domain object).
        The supplied concepts are grandfathered in the same way as
        ``for_existing_publication``.
        """
        return cls(
            publication_types=_get_publication_types_for_kind(kind, allow_extra=publication_type),
            subject_types=_get_subject_types(allow_extra=subject_area),
        )

    def validate(
        self,
        publication_type: VocabularyConcept,
        subject_area: VocabularyConcept,
    ) -> None:
        """Validate that both concepts are within the allowed sets.

        Raises:
            InvalidPublicationType: if the publication type is not allowed.
            InvalidSubjectType: if the subject area is not allowed.
        """
        if not _is_concept_allowed(publication_type, self.publication_types):
            raise InvalidPublicationType(
                f"Publication type '{publication_type.concept_id}' is not allowed"
            )
        if not _is_concept_allowed(subject_area, self.subject_types):
            raise InvalidSubjectType(f"Subject area '{subject_area.concept_id}' is not allowed")
