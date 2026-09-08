from django.db.models import Exists, OuterRef, Prefetch, QuerySet

from coda.apps.contracts.models import Contract
from coda.apps.invoices import invoice_query
from coda.apps.invoices.models import (
    FundingAssignment,
    Position as PositionModel,
)


def get_contracts_for_export(
    params: invoice_query.InvoiceSearchParams,
) -> QuerySet[Contract]:
    criteria = invoice_query.build_criteria(params)
    matching_invoices = invoice_query.search(*criteria)

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
            # Scoped to matching invoices in SQL. Must come before the other
            # position_set lookups: Django caches the first position_set fetch
            # per contract and silently skips later ones.
            Prefetch(
                "position_set",
                queryset=PositionModel.objects.filter(invoice__in=matching_invoices)
                .select_related("invoice__creditor")
                .prefetch_related("invoice__currency_conversions"),
            ),
            Prefetch(
                "position_set__funding_assignments",
                queryset=FundingAssignment.objects.select_related("funding_source"),
            ),
        )
        .distinct()
    )

    return contracts
