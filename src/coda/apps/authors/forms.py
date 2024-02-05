from django import forms
from coda.apps.authors.models import Person


class PersonForm(forms.ModelForm[Person]):
    class Meta:
        model = Person
        fields = "__all__"
