import datetime
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple, cast

from django import forms
from django.forms.renderers import BaseRenderer
from django.forms.utils import ErrorList
from django.utils.datastructures import MultiValueDictKeyError

from coda.apps.formbase import CodaFormBase
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import LinkDto, PublicationMetaDto
from coda.apps.publications.models import Concept, LinkType, Publication
from coda.doi import Doi
from coda.publication import License, OpenAccessType, Published, UnpublishedState


def concept_json_value(concept: Concept) -> str:
    return json.dumps({"concept": concept.concept_id, "vocabulary": concept.vocabulary_id})


def concept_form_values(concepts: Iterable[Concept]) -> list[tuple[str, str]]:
    return [(concept_json_value(c), c.name) for c in concepts]


def concept_options_by_vocabulary(vocabulary_type: str) -> Callable[[], list[tuple[str, str]]]:
    def _concept_options_by_vocabulary() -> list[tuple[str, str]]:
        preferences, _ = GlobalPreferences.objects.get_or_create()
        if vocabulary_type == "publication_type":
            _concepts = preferences.default_publication_type_vocabulary.concepts
        elif vocabulary_type == "subject_area":
            _concepts = preferences.default_subject_classification_vocabulary.concepts
        else:
            raise ValueError("unknown vocabulary type")
        concepts = _concepts.all()
        return concept_form_values(concepts)

    return _concept_options_by_vocabulary


class Vocabularies(NamedTuple):
    subject_areas: Iterable[Concept] = ()
    publication_types: Iterable[Concept] = ()


class PublicationForm(CodaFormBase):
    use_required_attribute = False

    title = forms.CharField(required=True)
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
    )
    publication_type = forms.ChoiceField(
        choices=concept_options_by_vocabulary("publication_type"), required=False
    )
    subject_area = forms.ChoiceField(
        choices=concept_options_by_vocabulary("subject_area"), required=False
    )
    open_access_type = forms.ChoiceField(
        choices=Publication.OA_TYPES, required=True, initial=OpenAccessType.Closed.name
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

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        auto_id: bool | str = True,
        prefix: str | None = None,
        initial: Mapping[str, Any] | None = None,
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

    def _update_field_choices(self, field_name: str, vocabulary: Iterable[Concept]) -> None:
        if vocabulary:
            field: forms.Field = self.fields[field_name]
            self._as_choicefield(field).choices = concept_form_values(vocabulary)
            if field_name in self.errors:
                self.errors.pop(field_name)
                field.widget.attrs.pop("aria-invalid")

    def _as_choicefield(self, field: forms.Field) -> forms.ChoiceField:
        return cast(forms.ChoiceField, field)

    def full_clean(self) -> None:
        super().full_clean()
        if not hasattr(self, "cleaned_data"):
            return

        try:
            subject_area = json.loads(self.data["subject_area"])
            self.cleaned_data["subject_area"] = subject_area["concept"]
            self.cleaned_data["subject_area_vocabulary"] = subject_area["vocabulary"]
        except (json.decoder.JSONDecodeError, MultiValueDictKeyError):
            self.add_error("subject_area", "Invalid value for subject area")

        try:
            publication_type = json.loads(self.data["publication_type"])
            self.cleaned_data["publication_type"] = publication_type["concept"]
            self.cleaned_data["publication_type_vocabulary"] = publication_type["vocabulary"]
        except (json.decoder.JSONDecodeError, MultiValueDictKeyError):
            self.add_error("publication_type", "Invalid value for publication type")

        if self.cleaned_data.get("publication_state") != Published.name():
            return

        try:
            online_date = self.cleaned_data.get("online_publication_date")
            print_date = self.cleaned_data.get("print_publication_date")
            Published(online=online_date, print=print_date)
        except ValueError as err:
            self.add_error("online_publication_date", str(err))
            self.add_error("print_publication_date", str(err))

    def get_form_data(self) -> PublicationMetaDto:
        return PublicationMetaDto(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            subject_area=self.cleaned_data["subject_area"],
            subject_area_vocabulary=self.cleaned_data["subject_area_vocabulary"],
            publication_type=self.cleaned_data["publication_type"],
            publication_type_vocabulary=self.cleaned_data["publication_type_vocabulary"],
            open_access_type=self.cleaned_data["open_access_type"],
            publication_state=self.cleaned_data["publication_state"],
            online_publication_date=self._parse_date("online"),
            print_publication_date=self._parse_date("print"),
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
        if self.cleaned_data["link_type"] == "DOI":
            try:
                Doi(self.cleaned_data["link_value"])
            except ValueError as err:
                self.add_error("link_value", str(err))

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data["link_type"],
            link_value=self.cleaned_data.get("link_value", self.data.get("link_value", "")),
        )
