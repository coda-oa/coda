import datetime
import logging
from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple, cast

from django import forms

from coda.apps import widgets
from coda.apps.formbase import CodaFormBase
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import ConceptDto, LinkDto, PublicationMetaDto
from coda.apps.publications.models import LinkType, Publication
from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.publication import License, OpenAccessType, Published, UnpublishedState, links
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept, VocabularyProtocol

from ._fields import ConceptChoiceField, encode_concept_dto


def vocabulary_from_settings(vocabulary_type: str) -> VocabularyProtocol:
    match vocabulary_type:
        case "publication_type":
            vocabulary = GlobalPreferences.get_article_publication_type_vocabulary()
        case "subject_area":
            vocabulary = GlobalPreferences.get_subject_classification_vocabulary()
        case _:
            raise ValueError("unknown vocabulary type")
    return vocabulary


class Vocabularies(NamedTuple):
    subject_areas: VocabularyProtocol | None = None
    publication_types: VocabularyProtocol | None = None


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
        choices=lambda: vocabulary_from_settings("publication_type"),
        required=True,
        widget=widgets.SearchSelectWidget,
        label="Publication type*",
    )
    subject_area = ConceptChoiceField(
        choices=lambda: vocabulary_from_settings("subject_area"),
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
    def from_dto(cls, dto: PublicationMetaDto) -> "PublicationForm":
        subject_vocabulary_id = dto.subject_area.vocabulary
        if subject_vocabulary_id != UnknownConcept.vocabulary:
            subject_areas = vocabulary_repository.get_by_id(subject_vocabulary_id)
        else:
            subject_areas = None

        pub_type_vocabulary_id = dto.publication_type.vocabulary
        if pub_type_vocabulary_id != UnknownConcept.vocabulary:
            publication_types = vocabulary_repository.get_by_id(pub_type_vocabulary_id)
        else:
            publication_types = None

        vocabularies = Vocabularies(
            subject_areas=subject_areas,
            publication_types=publication_types,
        )

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
            vocabularies=vocabularies,
        )

    @classmethod
    def with_article_vocabulary(cls, data: Mapping[str, Any] | None = None) -> "PublicationForm":
        vocabularies = Vocabularies(
            subject_areas=GlobalPreferences.get_subject_classification_vocabulary(),
            publication_types=GlobalPreferences.get_article_publication_type_vocabulary(),
        )

        return cls(data, vocabularies=vocabularies)

    @classmethod
    def with_monograph_vocabulary(cls, data: Mapping[str, Any] | None = None) -> "PublicationForm":
        vocabularies = Vocabularies(
            subject_areas=GlobalPreferences.get_subject_classification_vocabulary(),
            publication_types=GlobalPreferences.get_monograph_publication_type_vocabulary(),
        )

        return cls(data, vocabularies=vocabularies)

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        vocabularies: Vocabularies = Vocabularies(),
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(data, *args, **kwargs)

        self._set_vocabulary("subject_area", vocabularies.subject_areas)
        self._set_vocabulary("publication_type", vocabularies.publication_types)
        logging.info(
            "PublicationForm initialized with vocabularies: subject_areas=%s, publication_types=%s",
            vocabularies.subject_areas,
            vocabularies.publication_types,
        )

        if data:
            _ = self.is_valid()

    def _set_vocabulary(self, field: str, vocabulary: VocabularyProtocol | None) -> None:
        cast(ConceptChoiceField, self.fields[field]).set_vocabulary(vocabulary)

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
