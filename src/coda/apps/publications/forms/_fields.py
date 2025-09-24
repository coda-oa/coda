import base64
from collections.abc import Callable
from typing import Any

from django import forms

from coda.apps.dto import CodaBaseDto
from coda.apps.publications.dto import ConceptDto
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept, VocabularyProtocol


class FormConceptInput(CodaBaseDto):
    vocabulary: int
    concept: str


def encode_concept(concept: VocabularyConcept) -> str:
    return _encode_concept(concept.vocabulary, concept.concept_id)


def encode_concept_dto(concept_dto: ConceptDto) -> str:
    return _encode_concept(concept_dto.vocabulary, concept_dto.concept)


def _encode_concept(vocabulary_id: int, concept_id: str) -> str:
    """Encode concept as vocabulary_id:base64_concept_id."""
    encoded_concept_id = base64.urlsafe_b64encode(concept_id.encode()).decode()
    return f"{vocabulary_id}:{encoded_concept_id}"


def decode_concept(value: str) -> FormConceptInput:
    if not value or ":" not in value:
        raise ValueError("Invalid concept value")

    vocabulary_id_str, encoded_concept_id = value.split(":", 1)
    concept_id = base64.urlsafe_b64decode(encoded_concept_id.encode()).decode()
    return FormConceptInput(vocabulary=int(vocabulary_id_str), concept=concept_id)


EMPTY_CHOICE = (encode_concept(UnknownConcept), "---------")


class ConceptChoiceField(forms.ChoiceField):
    """A ChoiceField that handles VocabularyConcept serialization."""

    vocabulary: VocabularyProtocol | None

    def __init__(
        self,
        vocabulary: VocabularyProtocol | Callable[[], VocabularyProtocol] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if callable(vocabulary):
            self.vocabulary = vocabulary()
        else:
            self.vocabulary = vocabulary

        if vocabulary:
            self._update_choices()

    def _update_choices(self) -> None:
        """Update choices from vocabulary."""
        if not self.vocabulary:
            self.choices = [EMPTY_CHOICE]
            return

        self.choices = [EMPTY_CHOICE] + [
            (encode_concept(concept), concept.name) for concept in self.vocabulary.concepts
        ]

    def clean(self, value: Any) -> VocabularyConcept | None:
        """Convert form value to VocabularyConcept."""
        if not value:
            return None

        try:
            form_concept = decode_concept(value)
        except (ValueError, IndexError) as e:
            raise forms.ValidationError(f"Invalid concept value: {e}")

        if (
            form_concept.vocabulary == UnknownConcept.vocabulary
            and form_concept.concept == UnknownConcept.concept_id
        ):
            return UnknownConcept

        if not self.vocabulary or self.vocabulary.id != form_concept.vocabulary:
            return None

        for concept in self.vocabulary.concepts:
            if concept.concept_id == form_concept.concept:
                return concept

        return None

    def set_vocabulary(self, vocabulary: VocabularyProtocol | None) -> None:
        """Update the vocabulary and refresh choices."""
        self.vocabulary = vocabulary
        self._update_choices()
