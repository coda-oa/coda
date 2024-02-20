from django import forms

from coda.apps.institutions.models import Institution


class PersonForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField()
    orcid = forms.CharField()


class InstitutionForm(forms.Form):
    name = forms.ChoiceField(
        choices=[(i.pk, i.name) for i in Institution.objects.all()], label="Affiliation"
    )
