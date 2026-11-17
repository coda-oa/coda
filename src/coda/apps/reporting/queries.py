"""The ORM fetch for the statistics fact set (plan §4).

The statistics page and the CSV export use the same filtered rows. Both call
:func:`fundingrequest_query.filtered`. This module adds its own prefetch
graph: the fact builder reads only corresponding authors, the publication's
journal, publisher, publication type and attached contracts,
its positions with invoices and funding assignments, and external funding.
A test asserts that both fetch shapes produce equal facts.
"""

from collections.abc import Sequence

from django.db.models import Prefetch, QuerySet

from coda.apps.authors.models import Author
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.models import ExternalFunding, FundingRequest
from coda.apps.invoices.models import FundingAssignment, Invoice
from coda.domain.author import Role


def fetch_requests(
    criteria: Sequence[fundingrequest_query.FundingRequestSearchCriteria],
) -> QuerySet[FundingRequest]:
    """The filtered funding requests, shaped for ``dataset.build_facts``."""
    corresponding_authors = Prefetch(
        "publication__relevant_authors",
        # build_facts reads corresponding authors only.
        queryset=Author.objects.filter(roles__in=Role.corresponding_role_names())
        .select_related("affiliation")
        .order_by("id"),
    )
    return (
        fundingrequest_query.filtered(*criteria)
        .select_related(
            "publication",
            "publication__article_journal__publisher",
            "publication__monograph_publisher",
            "publication__publication_type",
        )
        .prefetch_related(
            corresponding_authors,
            "publication__attached_contracts__contract",
            Prefetch(
                "publication__position_set__invoice",
                queryset=Invoice.objects.prefetch_related("currency_conversions"),
            ),
            Prefetch(
                "publication__position_set__funding_assignments",
                queryset=FundingAssignment.objects.select_related(
                    "funding_source", "funding_source__institution"
                ),
            ),
            Prefetch(
                "external_funding",
                queryset=ExternalFunding.objects.select_related("organization"),
            ),
        )
    )
