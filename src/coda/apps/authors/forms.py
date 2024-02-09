from django import forms


class PersonForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField()
    orcid = forms.CharField()
