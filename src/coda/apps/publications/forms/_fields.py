import base64
from collections.abc import Callable, Collection
from typing import Any

from django import forms

from coda.apps.dto import CodaBaseDto
from coda.apps.publications.dto import ConceptDto
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept


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

    _concepts: Collection[VocabularyConcept]

    def __init__(
        self,
        concepts: Collection[VocabularyConcept] | Callable[[], Collection[VocabularyConcept]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if callable(concepts):
            self._concepts = concepts()
        else:
            self._concepts = concepts or []

        if concepts:
            self._update_choices()

    def _update_choices(self) -> None:
        """Update choices from concepts."""
        if not self._concepts:
            self.choices = [EMPTY_CHOICE]
            return

        self.choices = [EMPTY_CHOICE] + [
            (encode_concept(concept), concept.name) for concept in self._concepts
        ]
        self.initial = EMPTY_CHOICE

    def clean(self, value: Any) -> VocabularyConcept:
        """Convert form value to VocabularyConcept."""
        if not value and self.required:
            raise forms.ValidationError("Please select a valid entry")

        try:
            form_concept = decode_concept(value)
        except (ValueError, IndexError) as e:
            raise forms.ValidationError(f"Invalid concept value: {e}")

        if (
            form_concept.vocabulary == UnknownConcept.vocabulary
            and form_concept.concept == UnknownConcept.concept_id
        ):
            return UnknownConcept

        if not self._concepts:
            raise forms.ValidationError("No concepts provided")

        for concept in self._concepts:
            if concept.concept_id == form_concept.concept:
                return concept

        raise forms.ValidationError(f"Invalid concept {form_concept.concept}")

    def set_vocabulary(self, concepts: Collection[VocabularyConcept] | None) -> None:
        """Update the concepts and refresh choices."""
        self._concepts = concepts or []
        self._update_choices()
