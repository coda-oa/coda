from django import forms

from coda.apps.fields import currency_field
from coda.apps.invoices.models import Creditor, FundingSource
from coda.domain.invoice import PaymentStatus
from coda.domain.money import Currency


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
    external_invoice_id = forms.CharField(
        max_length=255,
        required=False,
        label="External Invoice ID",
    )
    comment = forms.CharField(widget=forms.Textarea, required=False, label="Comment")

    def get_currency(self) -> Currency:
        return Currency.from_code(self.cleaned_data["currency"])


class CreditorForm(forms.ModelForm[Creditor]):
    class Meta:
        model = Creditor
        fields = "__all__"


class FundingSourceForm(forms.ModelForm[FundingSource]):
    class Meta:
        model = FundingSource
        fields = "__all__"
