from dataclasses import dataclass
from datetime import date
from typing import Any, TypedDict

from django import forms
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from pydantic import BaseModel, ConfigDict, Field, computed_field

from coda.apps.contracts.models import Contract
from coda.apps.exports.services.filter_display import (
    build_filter_form_context,
    filter_field_label,
    filters_from_querydict,
    publication_state_choices,
)
from coda.apps.fundingrequests.fundingrequest_query import (
    PaymentStatus as FundingRequestPaymentStatus,
)
from coda.apps.fundingrequests.fundingrequest_query import (
    PublicationEntityType,
)
from coda.apps.fundingrequests.models import Label
from coda.apps.invoices.models import FundingSource
from coda.domain.date import DateRange, InvalidDateRangeError
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import DecimalSeparator
from coda.domain.publication import OpenAccessType


class FundingRequestFilterForm(forms.Form):
    """Validation-only form for the shared export filter widgets.

    Rendered markup stays in generate_export_form.html; this form only
    validates the POSTed data (field names match the widget ``name`` attrs).
    """

    title = forms.CharField(required=False, max_length=255)
    period_start = forms.DateField(input_formats=("%Y-%m-%d",))
    period_end = forms.DateField(input_formats=("%Y-%m-%d",))
    decimal_separator = forms.TypedChoiceField(
        coerce=DecimalSeparator,
        choices=[(member.value, member.display) for member in DecimalSeparator],
        empty_value=None,
        required=False,
    )
    search_term = forms.CharField(required=False)
    processing_status = forms.TypedMultipleChoiceField(
        coerce=ReviewResult,
        choices=[(member.value, member.value) for member in ReviewResult],
        required=False,
    )
    payment_status = forms.TypedMultipleChoiceField(
        coerce=FundingRequestPaymentStatus,
        choices=[
            (member.value, member.value.replace("_", " ").title())
            for member in FundingRequestPaymentStatus
        ],
        required=False,
    )
    payment_methods = forms.TypedMultipleChoiceField(
        coerce=PaymentMethod,
        choices=[(member.value, member.value) for member in PaymentMethod],
        required=False,
    )
    open_access_type = forms.TypedMultipleChoiceField(
        coerce=OpenAccessType,
        choices=[(member.value, member.value) for member in OpenAccessType],
        required=False,
    )
    publication_states = forms.MultipleChoiceField(
        choices=publication_state_choices, required=False
    )
    publication_type = forms.ChoiceField(
        choices=[(et.value, et.value) for et in PublicationEntityType], required=False
    )
    labels = forms.ModelMultipleChoiceField(queryset=Label.objects.all(), required=False)
    exclude_labels = forms.ModelMultipleChoiceField(queryset=Label.objects.all(), required=False)
    funding_source = forms.ModelChoiceField(
        queryset=FundingSource.objects.filter(type="budget"), required=False
    )
    contract_name = forms.ModelChoiceField(queryset=Contract.objects.all(), required=False)
    contract_year = forms.IntegerField(required=False)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        start = cleaned.get("period_start")
        end = cleaned.get("period_end")
        if start is not None and end is not None:
            try:
                DateRange(start, end)
            except InvalidDateRangeError as error:
                self.add_error("period_end", str(error))
        return cleaned


class FilterCleanedData(TypedDict):
    """Exact shape of ``FundingRequestFilterForm.cleaned_data``.

    Django types ``cleaned_data`` as ``dict[str, Any]``; this names the
    per-key types the form guarantees (all fields are always present, empty
    optionals arrive as ``""`` / ``[]`` / ``None`` / empty queryset).
    """

    title: str
    period_start: date
    period_end: date
    decimal_separator: DecimalSeparator | None
    search_term: str
    processing_status: list[ReviewResult]
    payment_status: list[FundingRequestPaymentStatus]
    payment_methods: list[PaymentMethod]
    open_access_type: list[OpenAccessType]
    publication_states: list[str]
    publication_type: str
    labels: QuerySet[Label]
    exclude_labels: QuerySet[Label]
    funding_source: FundingSource | None
    contract_name: Contract | None
    contract_year: int | None


@dataclass(frozen=True)
class FormFieldErrors:
    label: str
    errors: list[str]


def form_error_lines(form: forms.Form) -> list[FormFieldErrors]:
    return [
        FormFieldErrors(
            label=filter_field_label(field),
            errors=[str(error) for error in errors],
        )
        for field, errors in form.errors.items()
    ]


class ExportFormConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_title: str
    form_action_url_name: str = Field(exclude=True)
    parameters_title: str
    title_label: str
    title_placeholder: str
    cancel_url_name: str = Field(exclude=True)
    submit_button_text: str
    include_payment_status: bool
    include_decimal_separator: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def form_action_url(self) -> str:
        return reverse(self.form_action_url_name)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cancel_url(self) -> str:
        return reverse(self.cancel_url_name)


def build_export_form_context(
    request: HttpRequest,
    form: FundingRequestFilterForm,
    *,
    config: ExportFormConfig,
    form_errors: list[FormFieldErrors] | None = None,
    current_filters: dict[str, str | list[str]] | None = None,
) -> dict[str, object]:
    context = build_filter_form_context()
    context.update(config.model_dump())
    context["form"] = form
    context["expand_advanced_search"] = bool(request.GET) or form_errors is not None
    context["current_filters"] = current_filters or filters_from_querydict(request.GET)
    if form_errors is not None:
        context["form_errors"] = form_errors
    return context
