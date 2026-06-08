from datetime import date

from django.db.models import QuerySet

from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.fundingrequest_query import ContractId, FundingRequestSearchCriteria
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.exports.services.fundingrequest_csv.criteria import (
    InvoiceDateRangeCriteria,
    InvoicePaymentStatusCriteria,
    InvoiceCreditorCriteria,
    InvoiceFundingSourceCriteria,
)
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
    invoice_date_start: date | None = None,
    invoice_date_end: date | None = None,
    invoice_status: str | None = None,
    invoice_creditor: str = "",
    funding_source: FundingSourceId | None = None,
    contract: ContractId | None = None,
) -> QuerySet[FundingRequest]:

    criteria: list[FundingRequestSearchCriteria] = []

    criteria.append(fundingrequest_query.DateRangeCriteria(DateRange(period_start, period_end)))

    if review_results:
        criteria.append(fundingrequest_query.ReviewResultCriteria(review_results=review_results))
    if payment_statuses:
        criteria.append(
            fundingrequest_query.PaymentStatusCriteria(payment_statuses=payment_statuses)
        )
    if labels or exclude_labels:
        criteria.append(
            fundingrequest_query.LabelsSearchCriteria(
                include_labels=labels or [],
                exclude_labels=exclude_labels or [],
            )
        )
    if payment_methods:
        criteria.append(fundingrequest_query.PaymentMethodCriteria(payment_methods=payment_methods))
    if open_access_types:
        criteria.append(
            fundingrequest_query.OpenAccessTypeCriteria(open_access_types=open_access_types)
        )
    if publication_states:
        criteria.append(
            fundingrequest_query.PublicationStateCriteria(publication_states=publication_states)
        )
    if entity_type:
        criteria.append(fundingrequest_query.EntityTypeCriteria(entity_type=entity_type))
    if generic_search:
        criteria.append(fundingrequest_query.GenericSearchCriteria(search_term=generic_search))

    if invoice_date_start and invoice_date_end:
        criteria.append(InvoiceDateRangeCriteria(invoice_date_start, invoice_date_end))
    if invoice_status:
        criteria.append(InvoicePaymentStatusCriteria(payment_status=invoice_status))
    if invoice_creditor:
        criteria.append(InvoiceCreditorCriteria(creditor_name=invoice_creditor))
    if funding_source:
        criteria.append(InvoiceFundingSourceCriteria(funding_source=funding_source))
    if contract:
        criteria.append(fundingrequest_query.ContractSearchCriteria(contract=contract))

    qs = fundingrequest_query.search(*criteria)

    return qs.prefetch_related(
        "publication__position_set__invoice",
        "publication__position_set__invoice__creditor",
        "publication__position_set__invoice__currency_conversions",
        "publication__position_set__funding_assignments__funding_source",
    ).distinct()
