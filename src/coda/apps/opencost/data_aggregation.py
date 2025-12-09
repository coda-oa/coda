from datetime import date
from django.db.models import Prefetch, QuerySet
from coda.apps.contracts.models import Contract
from coda.apps.invoices.models import Invoice, Position
from coda.apps.publications.models import Publication


def get_publications_for_period(
    start_date: date,
    end_date: date,
) -> QuerySet[Publication]:
    invoices_in_period = get_invoices_for_period(start_date, end_date)

    publication_ids_with_positions = (
        Position.objects.filter(invoice__in=invoices_in_period)
        .values_list("publication_id", flat=True)
        .distinct()
    )

    contracts_in_period = get_contracts_for_period(start_date, end_date)

    publication_ids_attached_to_contracts = (
        Publication.objects.filter(
            attached_contracts__contract__in=contracts_in_period,
            attached_contracts__contract_year__gte=start_date.year,
            attached_contracts__contract_year__lte=end_date.year,
        )
        .values_list("id", flat=True)
        .distinct()
    )

    all_publication_ids = set(publication_ids_with_positions) | set(
        publication_ids_attached_to_contracts
    )

    positions_in_period = Position.objects.filter(invoice__in=invoices_in_period).select_related(
        "invoice", "invoice__creditor", "funding_source"
    )

    return (
        Publication.objects.filter(id__in=all_publication_ids)
        .select_related(
            "article_journal",
            "article_journal__publisher",
            "monograph_publisher",
        )
        .prefetch_related(
            "links",
            "relevant_authors",
            "attached_contracts",
            "attached_contracts__contract",
            Prefetch("position_set", queryset=positions_in_period),
        )
    )


def get_invoices_for_period(start_date: date, end_date: date) -> QuerySet[Invoice]:
    return (
        Invoice.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            status="paid",
        )
        .select_related("creditor")
        .prefetch_related(
            "positions",
            "positions__publication",
            "positions__publication__article_journal",
            "positions__publication__article_journal__publisher",
            "positions__publication__monograph_publisher",
        )
    )


def get_contracts_for_period(
    start_date: date,
    end_date: date,
) -> QuerySet[Contract]:
    invoices_in_period = get_invoices_for_period(start_date, end_date)

    contract_ids = (
        Position.objects.filter(
            invoice__in=invoices_in_period,
            contract__isnull=False,
        )
        .values_list("contract_id", flat=True)
        .distinct()
    )

    positions_in_period = Position.objects.filter(
        invoice__in=invoices_in_period,
        contract__isnull=False,
    ).select_related("invoice", "invoice__creditor")

    return Contract.objects.filter(id__in=contract_ids).prefetch_related(
        "publishers",
        "journals",
        Prefetch("position_set", queryset=positions_in_period),
    )
