"""Query functions for funding request list view.

Implements CQRS-lite pattern with optimized bulk queries to avoid N+1 problem.
"""

from django.db.models import QuerySet

from coda.apps.contracts import mapper as contract_mapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.queries import detail
from coda.apps.fundingrequests.queries.models import FundingRequestListItem
from coda.apps.publications.services import publications
from coda.domain.contract import ContractYear
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import PublicationPaymentStatus


def get_list_items(queryset: QuerySet[FundingRequestModel]) -> list[FundingRequestListItem]:
    """Convert Django queryset to list items with optimized bulk queries.

    Performance: ~3-5 queries total regardless of result count.

    Query breakdown:
    1. Input queryset (already optimized with select_related/prefetch)
    2. Bulk fetch contracts for all publications
    3. Bulk fetch payments for all publications
    4. Additional select_related queries for related objects

    Args:
        queryset: Pre-filtered queryset from search/filter logic

    Returns:
        List of FundingRequestListItem ready for template rendering
    """
    fr_models = list(queryset)

    if not fr_models:
        return []

    publication_ids = [PublicationId(fr.publication.id) for fr in fr_models]
    payment_statuses = publications.get_payment_statuses(publication_ids)

    return [
        _build_list_item(fr_model, payment_statuses[PublicationId(fr_model.publication.id)])
        for fr_model in fr_models
    ]


def _has_invalid_contract_years(fr_model: FundingRequestModel) -> bool:
    """Check if any contract year is outside its contract period.

    Uses prefetched attached_contracts data - no additional queries.

    Args:
        fr_model: Funding request model with prefetched contracts

    Returns:
        True if ANY contract year is invalid (outside contract period)
    """

    attached_contracts = fr_model.publication.attached_contracts.all()

    for attached_contract in attached_contracts:
        contract = contract_mapper.as_domain_object(attached_contract.contract)
        contract_year = ContractYear(attached_contract.contract_year, contract)

        if not contract_year.is_in_contract_period():
            return True

    return False


def _build_list_item(
    fr_model: FundingRequestModel,
    payment_status: PublicationPaymentStatus,
) -> FundingRequestListItem:
    """Build list item from Django model and payment status.

    Combines article and monograph logic into single function.
    """
    if fr_model.publication.article_journal is not None:
        journal = fr_model.publication.article_journal
        return FundingRequestListItem(
            type="Article",
            id=fr_model.pk,
            url=fr_model.get_absolute_url(),
            request_id=fr_model.request_id,
            publication_title=fr_model.publication.title,
            authors=[a.name for a in fr_model.publication.relevant_authors.all()],
            publishing_entity_type="Journal",
            publishing_entity_name=journal.title,
            publishing_entity_url=journal.get_absolute_url(),
            updated_at=fr_model.updated_at.date(),
            labels=fr_model.labels.all(),
            status=fr_model.review.review_result,
            payment_status=detail._build_payment_details(payment_status, fr_model.request_id),
            publication_state=fr_model.publication.publication_state,
            journal_publisher_name=str(journal.publisher) if journal.publisher else None,
            journal_publisher_url=(
                journal.publisher.get_absolute_url() if journal.publisher else None
            ),
            has_invalid_contract_years=_has_invalid_contract_years(fr_model),
        )
    else:
        publisher = fr_model.publication.monograph_publisher
        assert publisher is not None

        return FundingRequestListItem(
            type="Monograph",
            id=fr_model.pk,
            url=fr_model.get_absolute_url(),
            request_id=fr_model.request_id,
            publication_title=fr_model.publication.title,
            authors=[a.name for a in fr_model.publication.relevant_authors.all()],
            publishing_entity_type="Publisher",
            publishing_entity_name=publisher.name,
            publishing_entity_url=publisher.get_absolute_url(),
            updated_at=fr_model.updated_at.date(),
            labels=fr_model.labels.all(),
            status=fr_model.review.review_result,
            payment_status=detail._build_payment_details(payment_status, fr_model.request_id),
            publication_state=fr_model.publication.publication_state,
            journal_publisher_name=None,
            journal_publisher_url=None,
            has_invalid_contract_years=_has_invalid_contract_years(fr_model),
        )
