from django import forms

from coda.apps import fields
from coda.apps.preferences.models import GlobalPreferences


class GlobalPreferencesForm(forms.ModelForm[GlobalPreferences]):
    home_currency = fields.currency_field(label="Home currency")

    class Meta:
        model = GlobalPreferences
        fields = "__all__"
        help_texts = {field.name: "" for field in GlobalPreferences._meta.get_fields()}
