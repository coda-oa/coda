from typing import Any

from django import forms

from coda.apps.journals import services
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.issn import Issn


def issn_validator(value: Any) -> None:
    try:
        Issn(value)
    except ValueError as e:
        raise forms.ValidationError(str(e))


class JournalForm(forms.ModelForm[Journal]):
    eissn = forms.CharField(max_length=9, label="E-ISSN", validators=[issn_validator])
    publisher = forms.ModelChoiceField(queryset=Publisher.objects.all().order_by("name"))

    def is_valid(self) -> bool:
        valid = super().is_valid()
        if not valid:
            return False

        existing_journal = services.find_by_eissn(self.cleaned_data["eissn"])
        if not existing_journal:
            return True

        if self.instance.pk != existing_journal.pk:
            self.add_error("eissn", "Journal with this E-ISSN already exists.")
            return False

        return True

    class Meta:
        model = Journal
        fields = ["title", "eissn", "publisher"]
        widgets = {
            "title": forms.TextInput(),
            "publisher": forms.Select(),
        }
