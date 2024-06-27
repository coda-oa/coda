import datetime
from typing import cast

from django import forms

from coda.apps.formbase import CodaFormBase
from coda.apps.publications.dto import LinkDto, PublicationMetaDto
from coda.apps.publications.models import Concept, LinkType, Publication
from coda.doi import Doi
from coda.publication import License, OpenAccessType, Published, UnpublishedState


class PublicationForm(CodaFormBase):
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
            publication_type=self.cleaned_data["publication_type"],
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
