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
from coda.domain.finance.invoice import FundingSourceId, PaymentStatus as InvoicePaymentStatus
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState

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

invoice_payment_status_choices: list[tuple[str, str]] = [
    (status.value, status.value.replace("_", " ").title()) for status in InvoicePaymentStatus
]


# ---------------------------------------------------------------------------
# Shared filter keys that are common to both CSV exports and openCost reports.
# ---------------------------------------------------------------------------

_COMMON_OPTIONAL_FILTER_FIELDS: list[str] = list(
    MULTI_VALUE_FILTER_FIELDS | SINGLE_VALUE_FILTER_FIELDS
)


def build_filters_from_request(
    request: HttpRequest,
    optional_fields: list[str] | None = None,
) -> dict[str, str]:
    """Build the raw filter dict from a POST request.

    By default, the common set of optional filter fields
    (``_COMMON_OPTIONAL_FILTER_FIELDS``) is used.  Pass ``optional_fields`` to
    use a different set instead.
    """
    filters: dict[str, str] = {
        "period_start": request.POST["period_start"],
        "period_end": request.POST["period_end"],
    }

    for field in optional_fields if optional_fields is not None else _COMMON_OPTIONAL_FILTER_FIELDS:
        values = [v for v in request.POST.getlist(field) if v]
        if values:
            filters[field] = ",".join(values)

    return filters


def parse_date_range(filters: dict[str, str]) -> DateRange | None:
    start_str = filters.get("period_start")
    end_str = filters.get("period_end")
    if start_str and end_str:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        end = datetime.strptime(end_str, "%Y-%m-%d").date()
        return DateRange(start, end)
    return None


def parse_funding_source(filters: dict[str, str]) -> FundingSourceId | None:
    raw = filters.get("funding_source")
    return FundingSourceId(int(raw)) if raw else None


def parse_invoice_payment_status(filters: dict[str, str]) -> InvoicePaymentStatus | None:
    raw = filters.get("payment_status", "")
    if not raw:
        return None
    statuses = [s.strip() for s in raw.split(",") if s]
    return InvoicePaymentStatus(statuses[0]) if statuses else None


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

    funding_source = parse_funding_source(filters)

    contract_raw = filters.get("contract_name") or filters.get("contract")
    contract_id = int(contract_raw) if contract_raw else None

    date_range = parse_date_range(filters)

    search_term = filters.get("search_term", "")

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
        if key in all_multi_value:
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
    )
    return [f for f in applied_filters if f is not None]


def build_applied_filters_for_contract(filters: dict[str, str]) -> list[AppliedFilter]:
    applied_filters = (
        _period_filter(filters),
        _invoice_payment_status_filter(filters),
        _funding_source_filter(filters),
    )
    return [f for f in applied_filters if f is not None]


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
    return AppliedFilter(label="Processing Status", value=", ".join(statuses))


def _payment_methods_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "payment_methods" not in filters:
        return None
    methods = [m.strip() for m in filters["payment_methods"].split(",") if m]
    return AppliedFilter(label="Payment Methods", value=", ".join(methods))


def _open_access_type_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "open_access_type" not in filters:
        return None
    types = [t.strip() for t in filters["open_access_type"].split(",") if t]
    return AppliedFilter(label="Open Access Type", value=", ".join(types))


def _publication_states_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "publication_states" not in filters:
        return None
    states = [s.strip() for s in filters["publication_states"].split(",") if s]
    return AppliedFilter(label="Publication States", value=", ".join(states))


def _labels_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "labels" not in filters:
        return None
    label_ids = [int(_id) for _id in filters["labels"].split(",") if _id]
    labels = Label.objects.filter(id__in=label_ids)
    return AppliedFilter(
        label="Labels",
        value=", ".join(label.name for label in labels),
    )


def _exclude_labels_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "exclude_labels" not in filters:
        return None
    exclude_label_ids = [int(_id) for _id in filters["exclude_labels"].split(",") if _id]
    exclude_labels = Label.objects.filter(id__in=exclude_label_ids)
    return AppliedFilter(
        label="Excluded Labels",
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
    return AppliedFilter(label="Payment Status", value=", ".join(statuses))


def _publication_type_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "publication_type" not in filters:
        return None
    types = [t.strip() for t in filters["publication_type"].split(",") if t]
    return AppliedFilter(label="Publication Type", value=", ".join(types))


def _contract_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "contract_name" not in filters:
        return None
    contract_ids = [int(_id) for _id in filters["contract_name"].split(",") if _id]
    contracts = Contract.objects.filter(id__in=contract_ids)
    return AppliedFilter(
        label="Contracts",
        value=", ".join(contract.name for contract in contracts),
    )


def _invoice_payment_status_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "payment_status" not in filters:
        return None
    statuses = [
        InvoicePaymentStatus(s.strip()).value.replace("_", " ").title()
        for s in filters["payment_status"].split(",")
        if s
    ]
    return AppliedFilter(label="Payment Status", value=", ".join(statuses))


def _funding_source_filter(filters: dict[str, str]) -> AppliedFilter | None:
    if "funding_source" not in filters:
        return None
    funding_source_ids = [int(_id) for _id in filters["funding_source"].split(",") if _id]
    funding_sources = FundingSource.objects.filter(id__in=funding_source_ids)
    return AppliedFilter(
        label="Funding Source",
        value=", ".join(source.name for source in funding_sources),
    )
