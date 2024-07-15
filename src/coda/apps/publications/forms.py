from collections.abc import Callable
import datetime
import json
from typing import cast

from django import forms

from coda.apps.formbase import CodaFormBase
from coda.apps.publications.dto import LinkDto, PublicationMetaDto
from coda.apps.publications.models import Concept, LinkType, Publication
from coda.doi import Doi
from coda.publication import License, OpenAccessType, Published, UnpublishedState


def concept_json_value(concept: Concept) -> str:
    return json.dumps({"concept": concept.concept_id, "vocabulary": concept.vocabulary_id})


def concept_options_by_vocabulary(vocabulary_name: str) -> Callable[[], list[tuple[str, str]]]:
    def _concept_options_by_vocabulary() -> list[tuple[str, str]]:
        return [
            (concept_json_value(c), c.name)
            for c in Concept.objects.filter(vocabulary__name=vocabulary_name)
        ]

    return _concept_options_by_vocabulary


class PublicationForm(CodaFormBase):
    use_required_attribute = False

    title = forms.CharField(required=True)
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
    )
    publication_type = forms.ChoiceField(
        choices=concept_options_by_vocabulary("COAR Resource Types"), required=False
    )
    subject_area = forms.ChoiceField(
        choices=concept_options_by_vocabulary("DFG Subject Classification"), required=False
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

    def full_clean(self) -> None:
        super().full_clean()
        if not hasattr(self, "cleaned_data"):
            return

        try:
            subject_area = json.loads(self.data["subject_area"])
            publication_type = json.loads(self.data["publication_type"])
            self.cleaned_data["subject_area"] = subject_area["concept"]
            self.cleaned_data["subject_area_vocabulary"] = subject_area["vocabulary"]
            self.cleaned_data["publication_type"] = publication_type["concept"]
            self.cleaned_data["publication_type_vocabulary"] = publication_type["vocabulary"]
        except json.decoder.JSONDecodeError:
            pass

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
