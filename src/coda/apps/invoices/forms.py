from typing import Self
from django import forms

from coda.apps.fields import currency_field
from coda.apps.invoices.models import Creditor, FundingSource
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.domain.invoice import CreditorId, Invoice, PaymentStatus
from coda.domain.money import Currency


class InvoiceForm(forms.Form):
    use_required_attribute = False
    number = forms.CharField(max_length=255, label="Invoice Number*")
    date = forms.DateField(widget=forms.TextInput(attrs={"type": "date"}), label="Invoice Date*")
    creditor = forms.ModelChoiceField[Creditor](queryset=Creditor.objects.all(), label="Creditor*")
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

    @classmethod
    def from_invoice(cls, invoice: Invoice) -> Self:
        return cls(
            {
                "number": invoice.number,
                "creditor": invoice.creditor,
                "date": invoice.date,
                "status": invoice.status.value,
                "comment": invoice.comment,
                "currency": invoice.currency().code,
                "external_invoice_id": invoice.external_invoice_id,
            }
        )

    def invoice_head(self) -> InvoiceHeadDto:
        return InvoiceHeadDto(
            number=self.cleaned_data["number"],
            date=self.cleaned_data["date"],
            status=PaymentStatus(self.cleaned_data["status"]),
            creditor=CreditorId(self.cleaned_data["creditor"].id),
            comment=self.cleaned_data["comment"],
            external_invoice_id=self.cleaned_data["external_invoice_id"],
            currency=self.get_currency(),
        )

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
