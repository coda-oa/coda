from typing import TypedDict

from django import forms

from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import LinkType, Publication


class PublicationFormData(TypedDict):
    title: str
    license: str
    open_access_type: str
    publication_state: str
    publication_date: str


class PublicationForm(forms.Form):
    use_required_attribute = False

    title = forms.CharField(required=True)
    license = forms.ChoiceField(choices=Publication.LICENSE_CHOICES, required=True)
    open_access_type = forms.ChoiceField(choices=Publication.OA_TYPES, required=True)
    publication_state = forms.ChoiceField(choices=Publication.STATES, required=True)
    publication_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def get_form_data(self) -> PublicationFormData:
        return PublicationFormData(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            open_access_type=self.cleaned_data["open_access_type"],
            publication_state=self.cleaned_data["publication_state"],
            publication_date=str(self.cleaned_data["publication_date"]),
        )


class LinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ModelChoiceField(queryset=LinkType.objects.all())
    link_value = forms.CharField()

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data["link_type"].pk,
            link_value=self.cleaned_data["link_value"],
        )
