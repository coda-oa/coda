from django import forms

from coda.apps.preferences.models import GlobalPreferences
from coda.domain.money import Currency


class GlobalPreferencesForm(forms.ModelForm[GlobalPreferences]):
    class Meta:
        model = GlobalPreferences
        fields = "__all__"
        widgets = {"home_currency": forms.Select(choices=[(c.code, c.code) for c in Currency])}
        help_texts = {field.name: "" for field in GlobalPreferences._meta.get_fields()}
