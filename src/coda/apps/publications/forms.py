from django import forms
from coda.apps.journals.models import Journal

from coda.apps.publications.models import LinkType, Publication, PublicationDto


class PublicationForm(forms.Form):
    title = forms.CharField()
    publication_state = forms.ChoiceField(
        choices=Publication.STATES, initial=Publication.State.SUBMITTED
    )
    publication_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    journal = forms.ModelChoiceField(queryset=Journal.objects.all())

    def to_dto(self) -> PublicationDto:
        return PublicationDto(
            title=self.cleaned_data["title"],
            journal=self.cleaned_data["journal"].pk,
            publication_state=self.cleaned_data["publication_state"],
            publication_date=str(self.cleaned_data["publication_date"]),
        )


class LinkForm(forms.Form):
    link_type = forms.ModelChoiceField(queryset=LinkType.objects.all())
    link = forms.URLField(label="")
