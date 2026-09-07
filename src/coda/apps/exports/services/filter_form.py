from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from django import forms
from django.db.models import QuerySet
from django.http import QueryDict

from coda.apps.contracts.models import Contract
from coda.apps.exports.services.filter_display import (
    MULTI_VALUE_FILTER_FIELDS,
    SINGLE_VALUE_FILTER_FIELDS,
    filter_field_label,
    publication_state_choices,
)
from coda.apps.fundingrequests.models import Label
from coda.apps.invoices.models import FundingSource
from coda.apps.fundingrequests.fundingrequest_query import (
    PaymentStatus as FundingRequestPaymentStatus,
    PublicationEntityType,
)
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


def current_filters_from_post(post: QueryDict) -> dict[str, str | list[str]]:
    """Preselect values for re-rendering the form after validation errors."""
    filters: dict[str, str | list[str]] = {}
    for key in MULTI_VALUE_FILTER_FIELDS:
        values = post.getlist(key)
        if values:
            filters[key] = values
    for key in SINGLE_VALUE_FILTER_FIELDS:
        values = post.getlist(key)
        if values:
            filters[key] = values[0]
    return filters


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
