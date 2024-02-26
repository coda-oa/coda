from django import forms

from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.models import LinkType, Publication


class PublicationForm(forms.Form):
    title = forms.CharField()
    publication_state = forms.ChoiceField(
        choices=Publication.STATES, initial=Publication.State.SUBMITTED
    )
    publication_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def to_dto(self) -> PublicationDto:
        return PublicationDto(
            title=self.cleaned_data["title"],
            publication_state=self.cleaned_data["publication_state"],
            publication_date=str(self.cleaned_data["publication_date"]),
        )


class LinkForm(forms.Form):
    link_type = forms.ModelChoiceField(queryset=LinkType.objects.all())
    link = forms.URLField(label="")
