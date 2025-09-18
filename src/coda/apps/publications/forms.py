import datetime
from collections.abc import Callable, Iterable, Mapping, MutableMapping
import logging
from typing import Any, NamedTuple, cast

import pydantic
from django import forms
from django.forms.renderers import BaseRenderer
from django.forms.utils import ErrorList
from django.utils.datastructures import MultiValueDictKeyError

from coda.apps import widgets
from coda.apps.formbase import CodaFormBase
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import ConceptDto, LinkDto, PublicationMetaDto
from coda.apps.publications.models import Concept, LinkType, Publication, Vocabulary
from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.publication import License, OpenAccessType, Published, UnpublishedState, links
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept, VocabularyProtocol


def concept_choices_from_global_settings(
    vocabulary_type: str,
) -> Callable[[], list[tuple[str, str]]]:
    def _concept_options_by_vocabulary() -> list[tuple[str, str]]:
        vocabulary = vocabulary_from_settings(vocabulary_type)
        return concept_form_values(vocabulary.concepts)

    return _concept_options_by_vocabulary


def get_concepts(vocabulary: Vocabulary | None) -> Iterable[Concept]:
    if not vocabulary:
        return []

    return vocabulary.concepts.all()


class Vocabularies(NamedTuple):
    subject_areas: VocabularyProtocol | None = None
    publication_types: VocabularyProtocol | None = None


class PublicationForm(CodaFormBase):
    use_required_attribute = False

    title = forms.CharField(required=True)
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
    )
    publication_type = forms.ChoiceField(
        choices=concept_choices_from_global_settings("publication_type"),
        required=True,
        widget=widgets.SearchSelectWidget,
    )
    subject_area = forms.ChoiceField(
        choices=concept_choices_from_global_settings("subject_area"),
        required=True,
        widget=widgets.SearchSelectWidget,
    )
    open_access_type = forms.ChoiceField(
        choices=Publication.OA_TYPES,
        required=True,
        initial=OpenAccessType.Closed.name,
        label="Publication Open Access Type",
    )
    publication_state = forms.ChoiceField(
        choices=Publication.STATES, required=True, initial=UnpublishedState.Unknown.name
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
                "subject_area": dto.subject_area.model_dump_json(),
                "publication_type": dto.publication_type.model_dump_json(),
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
        files: Mapping[str, Any] | None = None,
        auto_id: bool | str = True,
        prefix: str | None = None,
        initial: MutableMapping[str, Any] | None = None,
        error_class: type[ErrorList] = ErrorList,
        label_suffix: str | None = None,
        empty_permitted: bool = False,
        field_order: list[str] | None = None,
        use_required_attribute: bool | None = None,
        renderer: BaseRenderer | None = None,
        vocabularies: Vocabularies = Vocabularies(),
    ) -> None:
        super().__init__(
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            field_order,
            use_required_attribute,
            renderer,
        )

        self._update_field_choices("subject_area", vocabularies.subject_areas)
        self._update_field_choices("publication_type", vocabularies.publication_types)
        if data:
            _ = self.is_valid()

    def _update_field_choices(self, field_name: str, vocabulary: VocabularyProtocol | None) -> None:
        field: forms.Field = self.fields[field_name]
        if vocabulary:
            choices = [(None, "-----------")] + concept_form_values(vocabulary.concepts)
            self._as_choicefield(field).choices = choices
            if field_name in self.errors:
                self.errors.pop(field_name)
                field.widget.attrs.pop("aria-invalid")

    def _as_choicefield(self, field: forms.Field) -> forms.ChoiceField:
        return cast(forms.ChoiceField, field)

    def full_clean(self) -> None:
        super().full_clean()
        if not hasattr(self, "cleaned_data"):
            return

        self._parse_concept("subject_area")
        self._parse_concept("publication_type")

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
        logging.info("PublicationForm has the following errors %s", self.errors)
        if self.errors:
            return False

        return valid

    def _parse_concept(self, field_name: str) -> None:
        try:
            logging.info("Concept %s has value %s", field_name, self.data[field_name])
            self.cleaned_data[field_name] = ConceptDto.model_validate_json(self.data[field_name])
        except (pydantic.ValidationError, MultiValueDictKeyError):
            # self.add_error(field_name, str(err))
            pass

    def to_dto(self) -> PublicationMetaDto:
        return PublicationMetaDto(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            subject_area=self.cleaned_data["subject_area"],
            publication_type=self.cleaned_data["publication_type"],
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


class LinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(choices=lambda: LinkType.objects.values_list("name", "name"))
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        try:
            links.create_link(self.cleaned_data["link_type"], self.cleaned_data["link_value"])
        except ValueError as err:
            self.add_error("link_value", str(err))

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data["link_type"],
            link_value=self.cleaned_data.get("link_value", self.data.get("link_value", "")),
        )


def vocabulary_from_settings(vocabulary_type: str) -> VocabularyProtocol:
    match vocabulary_type:
        case "publication_type":
            vocabulary = GlobalPreferences.get_article_publication_type_vocabulary()
        case "subject_area":
            vocabulary = GlobalPreferences.get_subject_classification_vocabulary()
        case _:
            raise ValueError("unknown vocabulary type")
    return vocabulary


def concept_json(concept: VocabularyConcept) -> str:
    return ConceptDto.from_concept(concept).model_dump_json()


def concept_form_values(concepts: Iterable[VocabularyConcept]) -> list[tuple[str, str]]:
    return [(concept_json(c), c.name) for c in concepts]
