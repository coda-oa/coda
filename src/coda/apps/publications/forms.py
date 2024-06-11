import datetime
from typing import TypedDict, cast

from django import forms

from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import Concept, LinkType, Publication
from coda.publication import License, OpenAccessType, UnpublishedState


class PublicationFormData(TypedDict):
    title: str
    license: str
    publication_type: str
    open_access_type: str
    online_publication_state: str
    online_publication_date: str
    print_publication_state: str
    print_publication_date: str


class PublicationForm(forms.Form):
    use_required_attribute = False

    title = forms.CharField(required=True)
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
    )
    publication_type = forms.ChoiceField(
        choices=lambda: [(v, n) for v, n in Concept.objects.values_list("concept_id", "name")],
        required=False,
    )
    open_access_type = forms.ChoiceField(
        choices=Publication.OA_TYPES, required=True, initial=OpenAccessType.Closed.name
    )
    online_publication_state = forms.ChoiceField(
        choices=Publication.STATES, required=True, initial=UnpublishedState.Unknown.name
    )
    online_publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    print_publication_state = forms.ChoiceField(
        choices=Publication.STATES, required=True, initial=UnpublishedState.Unknown.name
    )
    print_publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )

    def get_form_data(self) -> PublicationFormData:
        return PublicationFormData(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            publication_type=self.cleaned_data["publication_type"],
            open_access_type=self.cleaned_data["open_access_type"],
            online_publication_state=self.cleaned_data["online_publication_state"],
            online_publication_date=self._parse_date("online"),
            print_publication_state=self.cleaned_data["print_publication_state"],
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

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data["link_type"],
            link_value=self.cleaned_data["link_value"],
        )
