from datetime import datetime

from dataclasses import dataclass
from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse

from coda.apps.fundingrequests.models import Label
from coda.apps.contracts.models import Contract
from coda.apps.invoices.models import FundingSource
from coda.apps.fundingrequests.fundingrequest_query import (
    PaymentStatus as FundingRequestPaymentStatus,
    FundingRequestSearchParams,
    PublicationEntityType,
)
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState

FIELD_LABELS: dict[str, str] = {
    "period_start": "Period Start",
    "period_end": "Period End",
    "processing_status": "Processing Status",
    "payment_methods": "Payment Methods",
    "open_access_type": "Open Access Type",
    "publication_states": "Publication States",
    "labels": "Labels",
    "exclude_labels": "Excluded Labels",
    "payment_status": "Payment Status",
    "publication_type": "Publication Type",
    "contract_name": "Contracts",
    "funding_source": "Funding Source",
    "decimal_separator": "Decimal Separator",
    "search_term": "Search Term",
}


MULTI_VALUE_FILTER_FIELDS = {
    "open_access_type",
    "labels",
    "exclude_labels",
    "payment_status",
    "processing_status",
    "payment_methods",
    "publication_states",
}


SINGLE_VALUE_FILTER_FIELDS = {
    "publication_type",
    "funding_source",
    "contract_name",
    "period_start",
    "period_end",
    "search_term",
    "decimal_separator",
}


def parse_current_filters_to_context(request: HttpRequest) -> dict[str, str | list[str]]:
    filters: dict[str, str | list[str]] = {}
    for key in MULTI_VALUE_FILTER_FIELDS:
        values = request.GET.getlist(key)
        if values:
            filters[key] = values
    for key in SINGLE_VALUE_FILTER_FIELDS:
        values = request.GET.getlist(key)
        if values:
            filters[key] = values[0]
    return filters


# ---------------------------------------------------------------------------
# Shared choice lists used in both filter forms.
# ---------------------------------------------------------------------------
publication_state_choices: list[tuple[str, str]] = [
    ("Published", "Published"),
    *((s.name, s.value) for s in UnpublishedState),
]

payment_status_choices: list[tuple[str, str]] = [
    (status.value, status.value.replace("_", " ").title()) for status in FundingRequestPaymentStatus
]


def parse_common_filter_fields(filters: dict[str, str]) -> FundingRequestSearchParams:
    """Parse filter fields into a FundingRequestSearchParams object."""
    review_results = [
        ReviewResult(rr) for rr in filters.get("processing_status", "").split(",") if rr
    ]
    payment_statuses = [
        FundingRequestPaymentStatus(ps) for ps in filters.get("payment_status", "").split(",") if ps
    ]
    labels = [int(_id) for _id in filters.get("labels", "").split(",") if _id]
    exclude_labels = [int(_id) for _id in filters.get("exclude_labels", "").split(",") if _id]
    payment_methods = [
        PaymentMethod(pm) for pm in filters.get("payment_methods", "").split(",") if pm
    ]
    open_access_types = [
        OpenAccessType(oat) for oat in filters.get("open_access_type", "").split(",") if oat
    ]
    publication_states = [ps for ps in filters.get("publication_states", "").split(",") if ps]

    entity_type_raw = filters.get("publication_type") or filters.get("entity_type")
    entity_type = (
        PublicationEntityType(entity_type_raw) if entity_type_raw else PublicationEntityType.All
    )

    funding_source_raw = filters.get("funding_source")
    funding_source = FundingSourceId(int(funding_source_raw)) if funding_source_raw else None

    contract_raw = filters.get("contract_name") or filters.get("contract")
    contract_id = int(contract_raw) if contract_raw else None

    # Parse date range
    start_str = filters.get("period_start")
    end_str = filters.get("period_end")
    date_range = None
    if start_str and end_str:
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
            date_range = DateRange(start, end)
        except ValueError:
            pass

    search_term = filters.get("search_term", "")

    decimal_separator = filters.get("decimal_separator", ".")
    if decimal_separator not in {".", ","}:
        decimal_separator = "."

    return FundingRequestSearchParams(
        date_range=date_range,
        review_results=review_results,
        payment_statuses=payment_statuses,
        labels=labels,
        exclude_labels=exclude_labels,
        payment_methods=payment_methods,
        open_access_types=open_access_types,
        publication_states=publication_states,
        entity_type=entity_type,
        search_term=search_term,
        contract_id=contract_id,
        funding_source=funding_source,
        decimal_separator=decimal_separator,
    )


def build_filter_form_context() -> dict[str, object]:
    """Return the template context dict needed to render any filter form.

    Both the CSV export form and the openCost generate form use exactly the
    same set of filter widgets, so the context they need is identical.
    """
    return {
        "processing_states": [rr.value for rr in ReviewResult],
        "payment_methods": [(pm.value, pm.value) for pm in PaymentMethod],
        "open_access_types": [oat.value for oat in OpenAccessType],
        "publication_states": publication_state_choices,
        "labels": Label.objects.all(),
        "funding_sources": FundingSource.objects.filter(type="budget"),
        "publication_types": [(et.value, et.value) for et in PublicationEntityType],
        "contract_list": Contract.objects.all(),
        "payment_status_choices": payment_status_choices,
    }


def create_redo_url(filters: dict[str, str], url_name: str) -> str:
    redo_params: dict[str, str | list[str]] = {}
    all_multi_value = MULTI_VALUE_FILTER_FIELDS | SINGLE_VALUE_FILTER_FIELDS
    for key, value in filters.items():
        if key in all_multi_value and key != "decimal_separator":
            redo_params[key] = value.split(",")
        else:
            redo_params[key] = value
    return reverse(url_name) + "?" + urlencode(redo_params, doseq=True)


@dataclass
class AppliedFilter:
    label: str
    value: str


def build_applied_filters(filters: dict[str, str]) -> list[AppliedFilter]:
    applied_filters = (
        _period_filter(filters),
        _processing_status_filter(filters),
        _payment_methods_filter(filters),
        _open_access_type_filter(filters),
        _publication_states_filter(filters),
        _labels_filter(filters),
        _exclude_labels_filter(filters),
        _payment_status_filter(filters),
        _publication_type_filter(filters),
        _contract_filter(filters),
        _funding_source_filter(filters),
        _decimal_separator_filter(filters),
    )
    return [f for f in applied_filters if f is not None]


def _decimal_separator_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "decimal_separator" not in filters:
        return None
    value = ", (e.g. German)" if filters["decimal_separator"] == "," else ". (English/ISO)"
    return AppliedFilter(label=FIELD_LABELS["decimal_separator"], value=value)


def _period_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "period_start" not in filters or "period_end" not in filters:
        return None
    start = datetime.strptime(filters["period_start"], "%Y-%m-%d").strftime("%B %-d, %Y")
    end = datetime.strptime(filters["period_end"], "%Y-%m-%d").strftime("%B %-d, %Y")
    return AppliedFilter(label="Period", value=f"{start} to {end}")


def _processing_status_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "processing_status" not in filters:
        return None
    statuses = [s.strip() for s in filters["processing_status"].split(",") if s]
    return AppliedFilter(label=FIELD_LABELS["processing_status"], value=", ".join(statuses))


def _payment_methods_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "payment_methods" not in filters:
        return None
    methods = [m.strip() for m in filters["payment_methods"].split(",") if m]
    return AppliedFilter(label=FIELD_LABELS["payment_methods"], value=", ".join(methods))


def _open_access_type_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "open_access_type" not in filters:
        return None
    types = [t.strip() for t in filters["open_access_type"].split(",") if t]
    return AppliedFilter(label=FIELD_LABELS["open_access_type"], value=", ".join(types))


def _publication_states_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "publication_states" not in filters:
        return None
    states = [s.strip() for s in filters["publication_states"].split(",") if s]
    return AppliedFilter(label=FIELD_LABELS["publication_states"], value=", ".join(states))


def _labels_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "labels" not in filters:
        return None
    label_ids = [int(_id) for _id in filters["labels"].split(",") if _id]
    labels = Label.objects.filter(id__in=label_ids)
    return AppliedFilter(
        label=FIELD_LABELS["labels"],
        value=", ".join(label.name for label in labels),
    )


def _exclude_labels_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "exclude_labels" not in filters:
        return None
    exclude_label_ids = [int(_id) for _id in filters["exclude_labels"].split(",") if _id]
    exclude_labels = Label.objects.filter(id__in=exclude_label_ids)
    return AppliedFilter(
        label=FIELD_LABELS["exclude_labels"],
        value=", ".join(label.name for label in exclude_labels),
    )


def _payment_status_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "payment_status" not in filters:
        return None
    statuses = [
        FundingRequestPaymentStatus(s.strip()).value.replace("_", " ").title()
        for s in filters["payment_status"].split(",")
        if s
    ]
    return AppliedFilter(label=FIELD_LABELS["payment_status"], value=", ".join(statuses))


def _publication_type_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "publication_type" not in filters:
        return None
    types = [t.strip() for t in filters["publication_type"].split(",") if t]
    return AppliedFilter(label=FIELD_LABELS["publication_type"], value=", ".join(types))


def _contract_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "contract_name" not in filters:
        return None
    contract_ids = [int(_id) for _id in filters["contract_name"].split(",") if _id]
    contracts = Contract.objects.filter(id__in=contract_ids)
    return AppliedFilter(
        label=FIELD_LABELS["contract_name"],
        value=", ".join(contract.name for contract in contracts),
    )


def _funding_source_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "funding_source" not in filters:
        return None
    funding_source_ids = [int(_id) for _id in filters["funding_source"].split(",") if _id]
    funding_sources = FundingSource.objects.filter(id__in=funding_source_ids)
    return AppliedFilter(
        label=FIELD_LABELS["funding_source"],
        value=", ".join(source.name for source in funding_sources),
    )
