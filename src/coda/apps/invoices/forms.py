from django import forms

from coda.apps.fields import currency_field
from coda.apps.invoices.models import Creditor
from coda.invoice import PaymentStatus


class InvoiceForm(forms.Form):
    use_required_attribute = False
    number = forms.CharField(max_length=255, label="Invoice Number")
    date = forms.DateField(widget=forms.TextInput(attrs={"type": "date"}), label="Invoice Date")
    creditor = forms.ModelChoiceField[Creditor](queryset=Creditor.objects.all())
    currency = currency_field()
    status = forms.ChoiceField(
        choices=[(s.value, s.value) for s in PaymentStatus],
        initial=PaymentStatus.Unpaid.value,
    )
    comment = forms.CharField(widget=forms.Textarea, required=False, label="Comment")


class CreditorForm(forms.ModelForm[Creditor]):
    class Meta:
        model = Creditor
        fields = "__all__"
