from django import forms

from coda.apps.publications.models import LinkType, Publication


class PublicationForm(forms.Form):
    title = forms.TextInput()
    publication_state = forms.ChoiceField(
        choices=Publication.STATES, initial=Publication.State.SUBMITTED
    )
    publication_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class LinkForm(forms.Form):
    link_type = forms.ChoiceField(
        choices=[(link.pk, link.name) for link in LinkType.objects.all()], label=""
    )
    link = forms.URLField(label="")
