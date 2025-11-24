from datetime import date
from django.db.models import QuerySet
from coda.apps.invoices.models import Invoice, Position
from coda.apps.publications.models import Publication


def get_publications_for_period(
    start_date: date,
    end_date: date,
) -> QuerySet[Publication]:
    invoices_in_period = get_invoices_for_period(start_date, end_date)

    publication_ids = (
        Position.objects.filter(invoice__in=invoices_in_period)
        .values_list("publication_id", flat=True)
        .distinct()
    )

    return (
        Publication.objects.filter(id__in=publication_ids)
        .select_related(
            "article_journal",
            "article_journal__publisher",
            "monograph_publisher",
        )
        .prefetch_related(
            "links",
            "relevant_authors",
            "position_set",
            "position_set__invoice",
            "position_set__invoice__creditor",
            "position_set__funding_source",
        )
    )


def get_invoices_for_period(start_date: date, end_date: date) -> QuerySet[Invoice]:
    return (
        Invoice.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
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
