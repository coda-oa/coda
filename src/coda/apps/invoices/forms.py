from django import forms

from coda.apps.invoices.models import Creditor
from coda.money import Currency


class InvoiceForm(forms.Form):
    use_required_attribute = False
    number = forms.CharField(max_length=255, label="Invoice Number")
    date = forms.DateField(widget=forms.TextInput(attrs={"type": "date"}), label="Invoice Date")
    creditor = forms.ModelChoiceField(queryset=Creditor.objects.all())
    currency = forms.ChoiceField(
        choices=[(c.code, c.code) for c in Currency], initial=Currency.EUR.code
    )
    comment = forms.CharField(widget=forms.Textarea, required=False, label="Comment")


class CreditorForm(forms.ModelForm[Creditor]):
    class Meta:
        model = Creditor
        fields = "__all__"
