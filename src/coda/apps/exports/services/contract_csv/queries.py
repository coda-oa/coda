from django.db.models import Exists, OuterRef, Prefetch, QuerySet

from coda.apps.contracts.models import Contract
from coda.apps.invoices import invoice_query
from coda.apps.invoices.models import (
    FundingAssignment,
    Invoice as InvoiceModel,
    Position as PositionModel,
)
from coda.domain.finance.invoice import InvoiceId


def get_contracts_for_export(
    params: invoice_query.InvoiceSearchParams,
) -> tuple[QuerySet[Contract], set[InvoiceId]]:
    criteria = invoice_query.build_criteria(params)
    matching_invoices = invoice_query.search(*criteria)

    matching_invoice_ids = {InvoiceId(pk) for pk in matching_invoices.values_list("pk", flat=True)}

    has_matching_position = Exists(
        PositionModel.objects.filter(
            contract_id=OuterRef("pk"),
            invoice__in=matching_invoices,
        )
    )

    contracts = (
        Contract.objects.filter(has_matching_position)
        .prefetch_related(
            "publishers",
            "journals",
            "links",
            "links__type",
            Prefetch(
                "position_set__invoice",
                queryset=InvoiceModel.objects.select_related("creditor").prefetch_related(
                    "currency_conversions",
                    "positions__funding_assignments__funding_source",
                    "positions__contract",
                ),
            ),
            Prefetch(
                "position_set__funding_assignments",
                queryset=FundingAssignment.objects.select_related("funding_source"),
            ),
        )
        .distinct()
    )

    return contracts, matching_invoice_ids
