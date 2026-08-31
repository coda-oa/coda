from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from django import forms
from django.db.models import QuerySet
from django.http import QueryDict

from coda.apps.contracts.models import Contract
from coda.apps.exports.services.filter_display import (
    FIELD_LABELS,
    MULTI_VALUE_FILTER_FIELDS,
    SINGLE_VALUE_FILTER_FIELDS,
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
from coda.domain.publication import OpenAccessType


class FundingRequestFilterForm(forms.Form):
    """Validation-only form for the shared export filter widgets.

    Rendered markup stays in generate_export_form.html; this form only
    validates the POSTed data (field names match the widget ``name`` attrs).
    """

    period_start = forms.DateField(input_formats=("%Y-%m-%d",))
    period_end = forms.DateField(input_formats=("%Y-%m-%d",))
    decimal_separator = forms.ChoiceField(
        choices=[(".", ". (English/ISO)"), (",", ", (e.g. German)")],
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


class FilterCleanedData(TypedDict):
    """Exact shape of ``FundingRequestFilterForm.cleaned_data``.

    Django types ``cleaned_data`` as ``dict[str, Any]``; this names the
    per-key types the form guarantees (all fields are always present, empty
    optionals arrive as ``""`` / ``[]`` / ``None`` / empty queryset).
    """

    period_start: date
    period_end: date
    decimal_separator: str
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


def _put_multi(filters: dict[str, str], key: str, values: list[str]) -> None:
    if values:
        filters[key] = ",".join(values)


def build_filters_from_cleaned_data(data: FilterCleanedData) -> dict[str, str]:
    """Serialize form cleaned_data into the persisted raw filter dict format.

    Keeps the historical format: ISO date strings, comma-joined multi values,
    optional keys omitted when empty.
    """
    filters: dict[str, str] = {
        "period_start": data["period_start"].isoformat(),
        "period_end": data["period_end"].isoformat(),
    }

    search_term = data["search_term"]
    if search_term:
        filters["search_term"] = search_term

    decimal_separator = data["decimal_separator"]
    if decimal_separator:
        filters["decimal_separator"] = decimal_separator

    publication_type = data["publication_type"]
    if publication_type:
        filters["publication_type"] = publication_type

    contract = data["contract_name"]
    if contract:
        filters["contract_name"] = str(contract.pk)

    funding_source = data["funding_source"]
    if funding_source:
        filters["funding_source"] = str(funding_source.pk)

    _put_multi(filters, "processing_status", [m.value for m in data["processing_status"]])
    _put_multi(filters, "payment_status", [m.value for m in data["payment_status"]])
    _put_multi(filters, "payment_methods", [m.value for m in data["payment_methods"]])
    _put_multi(filters, "open_access_type", [m.value for m in data["open_access_type"]])
    _put_multi(filters, "publication_states", list(data["publication_states"]))
    _put_multi(filters, "labels", [str(label.pk) for label in data["labels"]])
    _put_multi(filters, "exclude_labels", [str(label.pk) for label in data["exclude_labels"]])

    return filters


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
            label=FIELD_LABELS.get(field, field),
            errors=[str(error) for error in errors],
        )
        for field, errors in form.errors.items()
    ]
