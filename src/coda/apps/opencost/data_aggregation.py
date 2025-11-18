from datetime import date
from django.db.models import QuerySet
from coda.apps.publications.models import Publication


def get_publications_for_period(
    start_date: date,
    end_date: date,
) -> QuerySet[Publication]:
    return (
        Publication.objects.filter(
            online_publication_date__gte=start_date,
            online_publication_date__lte=end_date,
        )
        .select_related(
            "article_journal",
            "article_journal__publisher",
            "monograph_publisher",
        )
        .prefetch_related(
            "links",
            "relevant_authors",
            # Invoice data for cost information
            "position_set",  # Publication positions
            "position_set__invoice",  # The invoices those positions belong to
            "position_set__invoice__creditor",  # Invoice creditor info
            "position_set__funding_source",  # Funding source (potential institution link)
        )
    )
