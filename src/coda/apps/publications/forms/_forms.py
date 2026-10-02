import datetime
import logging
from collections.abc import Collection, Iterable, Mapping
from typing import Any, cast

from django import forms

from coda.apps import widgets
from coda.apps.formbase import CodaFormBase
from coda.apps.publications.dto import ConceptDto, LinkDto, PublicationMetaDto
from coda.apps.publications.models import LinkType, Publication, Vocabulary
from coda.apps.publications.repositories import vocabulary_repository
from coda.contexts.fundingrequest.services.allowed_vocabularies import AllowedConcepts
from coda.domain.publication import License, OpenAccessType, Published, UnpublishedState, links
from coda.domain.vocabulary import (
    LimitedVocabulary,
    VocabularyConcept,
    VocabularyId,
    VocabularyProtocol,
)

from ._fields import ConceptChoiceField, encode_concept_dto


class PublicationForm(CodaFormBase):
    use_required_attribute = False

    title = forms.CharField(required=True, label="Title*")
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
        label="License*",
    )
    publication_type = ConceptChoiceField(
        concepts=[],
        required=True,
        widget=widgets.SearchSelectWidget,
        label="Publication type*",
    )
    subject_area = ConceptChoiceField(
        concepts=[],
        required=True,
        widget=widgets.SearchSelectWidget,
        label="Subject area*",
    )
    open_access_type = forms.ChoiceField(
        choices=Publication.OA_TYPES,
        required=True,
        initial=OpenAccessType.Closed.name,
        label="Publication open access type*",
    )
    publication_state = forms.ChoiceField(
        choices=Publication.STATES,
        required=True,
        initial=UnpublishedState.Unknown.name,
        label="Publication state*",
    )
    online_publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    print_publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )

    @classmethod
    def from_dto(cls, dto: PublicationMetaDto, allowed: AllowedConcepts) -> "PublicationForm":
        return cls(
            data={
                "title": dto.title,
                "license": dto.license,
                "subject_area": encode_concept_dto(dto.subject_area),
                "publication_type": encode_concept_dto(dto.publication_type),
                "open_access_type": dto.open_access_type,
                "publication_state": dto.publication_state,
                "online_publication_date": dto.online_publication_date,
                "print_publication_date": dto.print_publication_date,
            },
            concepts=allowed,
        )

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        concepts: AllowedConcepts = AllowedConcepts((), ()),
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(data, *args, **kwargs)

        self._set_concepts("subject_area", concepts.subject_types)
        self._set_concepts("publication_type", concepts.publication_types)
        logging.debug(
            "PublicationForm initialized with concepts: subject_areas=%s, publication_types=%s",
            concepts.subject_types,
            concepts.publication_types,
        )

        if data:
            _ = self.is_valid()

    def _set_concepts(self, field: str, concepts: Collection[VocabularyConcept] | None) -> None:
        cast(ConceptChoiceField, self.fields[field]).set_vocabulary(concepts)

    def full_clean(self) -> None:
        super().full_clean()
        if not hasattr(self, "cleaned_data"):
            return

        if self.cleaned_data.get("publication_state") != Published.name():
            return

        try:
            online_date = self.cleaned_data.get("online_publication_date")
            print_date = self.cleaned_data.get("print_publication_date")
            Published(online=online_date, print=print_date)
        except ValueError as err:
            self.add_error("online_publication_date", str(err))
            self.add_error("print_publication_date", str(err))

    def is_valid(self) -> bool:
        self.full_clean()
        valid = super().is_valid()
        logging.info("PublicationForm has the following errors %s", self.errors.as_data())
        if self.errors:
            return False

        return valid

    def to_dto(self) -> PublicationMetaDto:
        return PublicationMetaDto(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            subject_area=ConceptDto.from_concept(self.cleaned_data["subject_area"]),
            publication_type=ConceptDto.from_concept(self.cleaned_data["publication_type"]),
            open_access_type=self.cleaned_data["open_access_type"],
            publication_state=self.cleaned_data["publication_state"],
            online_publication_date=self.cleaned_data["online_publication_date"],
            print_publication_date=self.cleaned_data["print_publication_date"],
        )

    def _parse_date(self, media: str) -> str:
        key = f"{media}_publication_date"
        if not self.cleaned_data.get(key):
            return ""

        return cast(datetime.date, self.cleaned_data[key]).isoformat()


def _link_type_choices() -> list[tuple[str, str]]:
    return [(lt, lt) for lt in LinkType.objects.values_list("name", flat=True)]


class LinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(choices=_link_type_choices)
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        if not self.cleaned_data.get("link_type") or not self.cleaned_data.get("link_value"):
            return

        try:
            links.create_link(self.cleaned_data["link_type"], self.cleaned_data["link_value"])
        except ValueError as err:
            self.add_error("link_value", str(err))

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data.get("link_type", self.data.get("link_type", "")),
            link_value=self.cleaned_data.get("link_value", self.data.get("link_value", "")),
        )


def concept_json(concept: VocabularyConcept) -> str:
    return ConceptDto.from_concept(concept).model_dump_json()


def concept_form_values(concepts: Iterable[VocabularyConcept]) -> list[tuple[str, str]]:
    return [(concept_json(c), c.name) for c in concepts]


class ConceptCodesField(forms.Field):
    """Checkbox group of concept ids posted by the vocabulary editor.

    The widget makes ``value_from_datadict`` read every posted value; membership
    in the base vocabulary is validated by the form's ``clean()`` because the
    valid set is only known once the vocabulary has been resolved.
    """

    widget = forms.CheckboxSelectMultiple

    def to_python(self, value: Any) -> list[str]:
        if value in self.empty_values:
            return []
        values = value if isinstance(value, list) else [value]
        return [str(v) for v in values if v not in (None, "")]


class LimitedVocabularyTargetForm(forms.Form):
    """Resolves which limited vocabulary a vocabulary-editing POST refers to.

    The vocabulary editor posts either an existing ``vocabulary_id`` (edit) or a
    ``base_vocabulary_id`` (create). The view layer used to ``int()`` these raw
    values and let unknown ids escape as 500s; this form turns every bad or
    ambiguous reference into a validation error and exposes the reconstructed
    in-memory ``LimitedVocabulary`` via :meth:`vocabulary`.
    """

    vocabulary_id = forms.IntegerField(required=False)
    base_vocabulary_id = forms.ModelChoiceField(
        queryset=Vocabulary.objects.filter(is_limited=False),
        required=False,
        empty_label=None,
    )
    allowed_concepts_check = ConceptCodesField(required=False)
    disallowed_concepts_check = ConceptCodesField(required=False)
    disallowed_concepts = ConceptCodesField(required=False)

    def __init__(self, data: Any = None, *args: Any, **kwargs: Any) -> None:
        if data is not None and data.get("vocabulary_id") == "None":
            data = data.copy()
            data["vocabulary_id"] = ""
        super().__init__(data, *args, **kwargs)
        self._vocabulary: LimitedVocabulary | None = None

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if self.has_error("vocabulary_id") or self.has_error("base_vocabulary_id"):
            return cleaned

        vocabulary_id = cleaned.get("vocabulary_id")
        base_vocabulary = cleaned.get("base_vocabulary_id")
        if (vocabulary_id is None) == (base_vocabulary is None):
            raise forms.ValidationError(
                "Either vocabulary_id or base_vocabulary_id must be provided"
            )

        if vocabulary_id is not None:
            try:
                self._vocabulary = vocabulary_repository.get_limited_by_id(
                    VocabularyId(vocabulary_id)
                )
            except vocabulary_repository.VocabularyNotFoundError as err:
                self.add_error("vocabulary_id", str(err))
        else:
            self._vocabulary = new_limited_vocabulary(
                vocabulary_repository.get_by_id(VocabularyId(cast(Vocabulary, base_vocabulary).pk))
            )
        if self._vocabulary is not None:
            base = self._vocabulary.base_vocabulary
            for key in (
                "allowed_concepts_check",
                "disallowed_concepts_check",
                "disallowed_concepts",
            ):
                unknown = [c for c in cleaned.get(key, []) if not base.has_concept(c)]
                if unknown:
                    self.add_error(key, f"Unknown concept ids: {', '.join(unknown)}")
        return cleaned

    def vocabulary(self) -> LimitedVocabulary:
        assert self._vocabulary is not None
        return self._vocabulary


class LimitedVocabularySaveForm(LimitedVocabularyTargetForm):
    vocabulary_name = forms.CharField(required=True, label="Vocabulary name")


def new_limited_vocabulary(base_vocabulary: VocabularyProtocol) -> LimitedVocabulary:
    return LimitedVocabulary(
        id=None,
        base_vocabulary=base_vocabulary,
        name=f"{base_vocabulary.name} (limited)",
        version=base_vocabulary.version,
    )
