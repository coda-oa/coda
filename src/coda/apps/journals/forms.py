from typing import Any

from django import forms

from coda.apps.journals.models import Journal
from coda.issn import Issn


def issn_validator(value: Any) -> None:
    try:
        Issn(value)
    except ValueError as e:
        raise forms.ValidationError(str(e))


class JournalForm(forms.ModelForm[Journal]):
    eissn = forms.CharField(max_length=9, label="E-ISSN", validators=[issn_validator])

    class Meta:
        model = Journal
        fields = ["title", "eissn", "publisher"]
        widgets = {
            "title": forms.TextInput(),
            "publisher": forms.Select(),
        }
