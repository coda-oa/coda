from django import forms
from coda.apps import widgets

from coda.apps.institutions.models import Institution


class InstitutionForm(forms.ModelForm[Institution]):
    class Meta:
        model = Institution
        fields = ["name", "parent"]

        widgets = {"parent": widgets.SearchSelectWidget()}
