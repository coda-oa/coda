import datetime
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, Self, cast

from django import forms

from coda.apps.contracts.models import Contract
from coda.apps.fields import currency_field
from coda.apps.invoices import invoice_query as iq
from coda.apps.invoices.models import Creditor, FundingSource
from coda.apps.listfilters import (
    DateRangeField,
    ListSortOrder,
    named_model_choices,
    valid_fields,
)
from coda.apps.widgets import SearchSelectWidget
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice, PaymentStatus
from coda.domain.money import Currency


class InvoiceForm(forms.Form):
    use_required_attribute = False
    number = forms.CharField(max_length=255, label="Invoice Number*")
    date = forms.DateField(widget=forms.TextInput(attrs={"type": "date"}), label="Invoice Date*")
    creditor = forms.ModelChoiceField[Creditor](
        queryset=Creditor.all_objects.all(), label="Creditor*"
    )
    currency = currency_field()
    status = forms.ChoiceField(
        choices=PaymentStatus.choices(),
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
        fields: ClassVar[list[str]] = ["name"]


class FundingSourceForm(forms.ModelForm[FundingSource]):
    budget_currency = currency_field(label="Currency")

    class Meta:
        model = FundingSource
        fields: ClassVar[list[str]] = [
            "name",
            "budget_amount",
            "budget_currency",
            "period_start",
            "period_end",
            "allow_over",
            "allowance_amount",
        ]

    def __init__(self, *args: Any, home_currency: Callable[[], Currency], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        instance = self.instance
        if not instance.pk or instance.type == "budget":
            # Budget rows must carry all accounting terms; the model's columns
            # are nullable only because institution rows share the table.
            for field_name in (
                "budget_amount",
                "budget_currency",
                "period_start",
                "period_end",
            ):
                self.fields[field_name].required = True
            # Budgets are denominated in the home currency: invoice conversion
            # rates target the home currency only, so it is the one currency
            # the balance pipeline can always reach. Not a choice — fixed at
            # creation, frozen on edit; a disabled field keeps the instance's
            # value on POST. The instance value wins over field.initial, so
            # legacy budgets keep their currency.
            self.fields["budget_currency"].disabled = True
            if not instance.pk:
                self.fields["budget_currency"].initial = home_currency().code
        else:
            # Institution rows carry no budget terms (and the currency field
            # is required by default) — editing one must not demand them.
            for field_name in (
                "budget_amount",
                "budget_currency",
                "period_start",
                "period_end",
            ):
                self.fields[field_name].required = False

        if instance.pk and instance.period_start and instance.period_start <= datetime.date.today():
            # The amount is immutable once the period has started: disabled
            # fields fall back to the instance's value on POST.
            self.fields["budget_amount"].disabled = True

    def clean_name(self) -> str:
        name: str = self.cleaned_data["name"]
        if self.instance.pk and self.instance.type != "budget":
            # Institution rows share the table and are managed elsewhere;
            # the uniqueness rule covers budget-type sources only.
            return name
        duplicate = (
            FundingSource.objects.filter(name=name, type="budget")
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if duplicate:
            raise forms.ValidationError("A funding source with this name already exists.")
        return name

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        start = cleaned.get("period_start")
        end = cleaned.get("period_end")
        if start and end and start > end:
            self.add_error("period_end", "The period start must not be after its end.")
        return cleaned


payment_status_choices = [("", "-------"), *PaymentStatus.choices()]


class InvoiceListFilterForm(forms.Form):
    """Validation for the list sidebar's GET params; field names match the filter widgets.

    A value that fails validation lands in ``form.errors`` and its criterion is
    dropped; the raw param stays in the URL so its chip keeps it removable.
    """

    def __init__(
        self,
        *args: Any,
        funding_sources: Iterable[FundingSource] = (),
        contracts: Iterable[Contract] = (),
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        cast(forms.Select, self.fields["funding_source"].widget).choices = named_model_choices(
            funding_sources
        )
        cast(SearchSelectWidget, self.fields["contract_name"].widget).choices = named_model_choices(
            contracts
        )

    search_term = forms.CharField(required=False)
    funding_source = forms.IntegerField(
        required=False,
        label="Funding Source",
        widget=forms.Select(attrs={"id": "funding_source"}),
    )
    contract_name = forms.IntegerField(
        required=False,
        label="Contract",
        widget=SearchSelectWidget(attrs={"id": "contract_name", "class": "w-100"}),
    )
    contract_year = forms.IntegerField(
        required=False,
        label="Contract Year",
        widget=forms.NumberInput(attrs={"id": "contract_year", "step": "1"}),
    )
    contract_positions_only = forms.BooleanField(required=False)
    has_external_id = forms.BooleanField(
        required=False,
        label="Show invoices without external IDs",
        widget=forms.CheckboxInput(attrs={"id": "has_external_id", "value": "true"}),
    )
    has_foreign_currency = forms.BooleanField(
        required=False,
        label="Show invoices with foreign currencies and without conversion",
        widget=forms.CheckboxInput(attrs={"id": "has_foreign_currency", "value": "true"}),
    )
    has_errors = forms.BooleanField(
        required=False,
        label="Show invoices with errors",
        widget=forms.CheckboxInput(attrs={"id": "has_errors", "value": "true"}),
    )
    payment_status = forms.TypedChoiceField(
        coerce=PaymentStatus,
        choices=payment_status_choices,
        required=False,
        label="Payment status",
        widget=forms.Select(attrs={"id": "payment_status"}),
    )
    date_range = DateRangeField(
        input_names=("date_start", "date_end"),
        input_ids=("date_start", "date_end"),
    )

    sort_by = forms.ChoiceField(
        choices=ListSortOrder.choices(),
        required=False,
        widget=forms.Select(attrs={"id": "sort_by", "class": "filter-sort"}),
    )

    def search_criteria(
        self, *, home_currency: Callable[[], Currency]
    ) -> tuple[list[iq.InvoiceSearchCriterion], ListSortOrder]:
        """Translate valid GET fields into criteria and their sort order."""
        cleaned = valid_fields(self)
        positions_only = bool(cleaned.get("contract_positions_only"))
        has_foreign_currency = bool(cleaned.get("has_foreign_currency"))
        funding_source = cleaned.get("funding_source")
        params = iq.InvoiceSearchParams(
            date_range=cleaned.get("date_range"),
            payment_status=cleaned.get("payment_status") or None,
            search_term=cleaned.get("search_term", ""),
            funding_source=FundingSourceId(funding_source) if funding_source else None,
            contract_id=cleaned.get("contract_name") or None,
            contract_positions_only=positions_only,
            contract_year=cleaned.get("contract_year") or None,
            contract_year_positions_only=positions_only,
            has_external_id=not bool(cleaned.get("has_external_id")),
            has_foreign_currency=has_foreign_currency,
            home_currency=home_currency() if has_foreign_currency else None,
            has_errors=bool(cleaned.get("has_errors")),
        )
        return iq.build_criteria(params), ListSortOrder.parse_or_default(cleaned.get("sort_by"))
