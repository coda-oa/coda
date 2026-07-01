from datetime import datetime

from dataclasses import dataclass

from django.http import HttpRequest

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


# ---------------------------------------------------------------------------
# Shared filter keys that are common to both CSV exports and openCost reports.
# ---------------------------------------------------------------------------
_COMMON_OPTIONAL_FILTER_FIELDS: list[str] = [
    "processing_status",
    "payment_methods",
    "open_access_type",
    "publication_states",
    "labels",
    "exclude_labels",
    "payment_status",
    "publication_type",
    "funding_source",
    "contract_name",
]


def build_filters_from_request(
    request: HttpRequest,
    extra_optional_fields: list[str] | None = None,
) -> dict[str, str]:
    """Build the raw filter dict from a POST request.

    Both CSV exports and openCost reports share the same set of base optional
    filter fields.  Pass ``extra_optional_fields`` to include additional fields
    (e.g. invoice date fields used only in the CSV flow).
    """
    filters: dict[str, str] = {
        "period_start": request.POST["period_start"],
        "period_end": request.POST["period_end"],
    }

    for field in _COMMON_OPTIONAL_FILTER_FIELDS + (extra_optional_fields or []):
        values = [v for v in request.POST.getlist(field) if v]
        if values:
            filters[field] = ",".join(values)

    return filters


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


@dataclass
class AppliedFilter:
    label: str
    value: str


def build_applied_filters(filters: dict[str, str]) -> list[AppliedFilter]:
    applied_filters = []

    if "period_start" in filters and "period_end" in filters:
        start = datetime.strptime(filters["period_start"], "%Y-%m-%d").strftime("%B %-d, %Y")
        end = datetime.strptime(filters["period_end"], "%Y-%m-%d").strftime("%B %-d, %Y")
        applied_filters.append(
            AppliedFilter(
                label="Period",
                value=f"{start} to {end}",
            )
        )

    if "processing_status" in filters:
        statuses = [status.strip() for status in filters["processing_status"].split(",") if status]
        applied_filters.append(
            AppliedFilter(
                label="Processing Status",
                value=", ".join(statuses),
            )
        )

    if "payment_methods" in filters:
        methods = [method.strip() for method in filters["payment_methods"].split(",") if method]
        applied_filters.append(
            AppliedFilter(
                label="Payment Methods",
                value=", ".join(methods),
            )
        )

    if "open_access_type" in filters:
        types = [oa_type.strip() for oa_type in filters["open_access_type"].split(",") if oa_type]
        applied_filters.append(
            AppliedFilter(
                label="Open Access Type",
                value=", ".join(types),
            )
        )

    if "publication_states" in filters:
        states = [state.strip() for state in filters["publication_states"].split(",") if state]
        applied_filters.append(
            AppliedFilter(
                label="Publication States",
                value=", ".join(states),
            )
        )

    if "labels" in filters:
        label_ids = [int(_id) for _id in filters["labels"].split(",") if _id]
        labels = Label.objects.filter(id__in=label_ids)
        applied_filters.append(
            AppliedFilter(
                label="Labels",
                value=", ".join(label.name for label in labels),
            )
        )

    if "exclude_labels" in filters:
        exclude_label_ids = [int(_id) for _id in filters["exclude_labels"].split(",") if _id]
        exclude_labels = Label.objects.filter(id__in=exclude_label_ids)
        applied_filters.append(
            AppliedFilter(
                label="Excluded Labels",
                value=", ".join(label.name for label in exclude_labels),
            )
        )

    if "payment_status" in filters:
        statuses = [
            FundingRequestPaymentStatus(status.strip()).value.replace("_", " ").title()
            for status in filters["payment_status"].split(",")
            if status
        ]
        applied_filters.append(
            AppliedFilter(
                label="Payment Status",
                value=", ".join(statuses),
            )
        )

    if "publication_type" in filters:
        types = [ptype.strip() for ptype in filters["publication_type"].split(",") if ptype]
        applied_filters.append(
            AppliedFilter(
                label="Publication Type",
                value=", ".join(types),
            )
        )

    if "contract_name" in filters:
        contract_ids = [int(_id) for _id in filters["contract_name"].split(",") if _id]
        contracts = Contract.objects.filter(id__in=contract_ids)
        applied_filters.append(
            AppliedFilter(
                label="Contracts",
                value=", ".join(contract.name for contract in contracts),
            )
        )

    if "funding_source" in filters:
        funding_source_ids = [int(_id) for _id in filters["funding_source"].split(",") if _id]
        funding_sources = FundingSource.objects.filter(id__in=funding_source_ids)
        applied_filters.append(
            AppliedFilter(
                label="Funding Source",
                value=", ".join(source.name for source in funding_sources),
            )
        )

    return applied_filters
