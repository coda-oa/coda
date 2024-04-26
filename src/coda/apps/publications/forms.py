import datetime
from typing import TypedDict, cast

from django import forms

from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import LinkType, Publication
from coda.publication import License, OpenAccessType, UnpublishedState


class PublicationFormData(TypedDict):
    title: str
    license: str
    open_access_type: str
    publication_state: str
    publication_date: str | None


class PublicationForm(forms.Form):
    use_required_attribute = False

    title = forms.CharField(required=True)
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
    )
    open_access_type = forms.ChoiceField(
        choices=Publication.OA_TYPES, required=True, initial=OpenAccessType.Closed.name
    )
    publication_state = forms.ChoiceField(
        choices=Publication.STATES, required=True, initial=UnpublishedState.Unknown.name
    )
    publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )

    def get_form_data(self) -> PublicationFormData:
        return PublicationFormData(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            open_access_type=self.cleaned_data["open_access_type"],
            publication_state=self.cleaned_data["publication_state"],
            publication_date=self._parse_date(),
        )

    def _parse_date(self) -> str | None:
        if not self.cleaned_data.get("publication_date"):
            return None

        return cast(datetime.date, self.cleaned_data["publication_date"]).isoformat()


class LinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(choices=lambda: LinkType.objects.values_list("name", "name"))
    link_value = forms.CharField()

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data["link_type"],
            link_value=self.cleaned_data["link_value"],
        )
