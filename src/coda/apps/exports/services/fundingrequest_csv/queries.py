from datetime import date

from django.db.models import Prefetch, QuerySet

from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.fundingrequest_query import ContractId
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import FundingAssignment, Invoice
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication.publication import OpenAccessType

type LabelId = int


def get_funding_requests_for_export(
    period_start: date,
    period_end: date,
    review_results: list[ReviewResult] | None = None,
    payment_statuses: list[fundingrequest_query.PaymentStatus] | None = None,
    labels: list[LabelId] | None = None,
    exclude_labels: list[LabelId] | None = None,
    payment_methods: list[PaymentMethod] | None = None,
    open_access_types: list[OpenAccessType] | None = None,
    publication_states: list[str] | None = None,
    entity_type: fundingrequest_query.PublicationEntityType | None = None,
    generic_search: str = "",
    funding_source: FundingSourceId | None = None,
    contract: ContractId | None = None,
) -> QuerySet[FundingRequest]:

    params = fundingrequest_query.FundingRequestSearchParams(
        date_range=DateRange(period_start, period_end),
        review_results=review_results,
        payment_statuses=payment_statuses,
        labels=labels,
        exclude_labels=exclude_labels,
        payment_methods=payment_methods,
        open_access_types=open_access_types,
        publication_states=publication_states,
        entity_type=entity_type or fundingrequest_query.PublicationEntityType.All,
        search_term=generic_search,
        funding_source=funding_source,
        contract_id=contract,
    )

    criteria = fundingrequest_query.build_criteria(params)

    qs = fundingrequest_query.search(*criteria)

    return (
        qs.select_related(
            "publication",
            "review",
            "extra_contact",
        )
        .prefetch_related(
            Prefetch(
                "publication__position_set__invoice",
                queryset=Invoice.objects.select_related("creditor").prefetch_related(
                    "currency_conversions",
                    "positions__funding_assignments__funding_source",
                    "positions__publication",
                    "positions__contract",
                ),
            ),
            "publication__position_set__invoice__creditor",
            "publication__position_set__invoice__currency_conversions",
            "publication__position_set__invoice__positions",
            "publication__position_set__invoice__positions__funding_assignments",
            "publication__position_set__invoice__positions__funding_assignments__funding_source",
            "publication__relevant_authors",
            "publication__relevant_authors__identifier",
            "publication__relevant_authors__affiliation",
            "publication__links",
            "publication__links__type",
            "publication__attached_contracts",
            "publication__attached_contracts__contract",
            "publication__subject_area",
            "publication__subject_area__vocabulary",
            "publication__publication_type",
            "publication__publication_type__vocabulary",
            "labels",
            "external_funding",
            "external_funding__organization",
            Prefetch(
                "publication__position_set__funding_assignments",
                queryset=FundingAssignment.objects.select_related("funding_source"),
            ),
        )
        .distinct()
    )
