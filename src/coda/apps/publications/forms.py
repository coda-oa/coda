from django import forms
from coda.apps.journals.models import Journal

from coda.apps.publications.models import LinkType, Publication


class PublicationForm(forms.Form):
    title = forms.CharField()
    publication_state = forms.ChoiceField(
        choices=Publication.STATES, initial=Publication.State.SUBMITTED
    )
    publication_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    journal = forms.ModelChoiceField(queryset=Journal.objects.all())


class LinkForm(forms.Form):
    link_type = forms.ModelChoiceField(queryset=LinkType.objects.all())
    link = forms.URLField(label="")
