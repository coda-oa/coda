from django import forms

from coda.apps.publishers.models import Publisher


class ContractForm(forms.Form):
    use_required_attribute = False

    name = forms.CharField(required=True)
    publishers = forms.ModelMultipleChoiceField(
        Publisher.objects.all(), widget=forms.CheckboxSelectMultiple(), required=True
    )
    start_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"type": "date"}))
