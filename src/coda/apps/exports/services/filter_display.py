from datetime import datetime

from dataclasses import dataclass


from coda.apps.fundingrequests.models import Label
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.fundingrequest_query import (
    PaymentStatus as FundingRequestPaymentStatus,
)


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

    if "invoice_date_start" in filters and "invoice_date_end" in filters:
        applied_filters.append(
            AppliedFilter(
                label="Invoice Date",
                value=f"{filters['invoice_date_start']} to {filters['invoice_date_end']}",
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

    return applied_filters
