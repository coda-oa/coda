"""Query functions for funding request detail view.

Function-based query service following CQRS-lite pattern:
- Read-side operations only
- Optimized DB queries with joins/prefetches
- Returns FundingRequestDetail view model (no domain objects in template context)
"""

from typing import Any

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.mappers import FundingRequestDetailMapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.institutions.models import Institution
from coda.apps.publications.services import publications as publication_service
from coda.contexts.fundingrequest.services import checks as checks_service
from coda.domain.author import InstitutionId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.publication import PublicationId

from .mappers import PaymentDetailMapper


def get_detail_context(fr_id: FundingRequestId) -> dict[str, Any]:
    """Get complete context for funding request detail view.

    Orchestrates all queries efficiently:
    1. Fetch Django model with prefetch — single query covering all display data
    2. Fetch affiliation names (institution lookup) and payment status
    3. Delegate all transformation to FundingRequestDetailMapper.map()
    4. Return context dict

    Args:
        fr_id: Funding request ID

    Returns:
        Context dict for template
    """
    fr_model = FundingRequestDetailMapper.prefetch(FundingRequestModel.objects.all()).get(
        pk=fr_id.pk
    )

    affiliation_names = _fetch_affiliation_names(list(fr_model.publication.relevant_authors.all()))
    payment_status = publication_service.get_payment_status(PublicationId(fr_model.publication_id))
    payment_details = PaymentDetailMapper.map(payment_status, fr_model.request_id)

    detail = FundingRequestDetailMapper.map(fr_model, affiliation_names, payment_details)
    checkrun = checks_service.get_checkrun(FundingRequestId(detail.id))

    return {
        "funding_request": detail,
        "publication": detail.publication,
        "contact": detail.contact,
        "external_funding": detail.external_funding,
        "updated_at": detail.updated_at,
        "labels": detail.labels,
        "label_form": ChooseLabelForm(),
        "checks": checkrun,
        "edit_submitter_url": detail.edit_submitter_url,
        "edit_funding_url": detail.edit_funding_url,
    }


def _fetch_affiliation_names(authors: list[AuthorModel]) -> dict[InstitutionId, str]:
    """Bulk-fetch institution names for a set of authors (single query)."""
    affiliation_ids = {a.affiliation_id for a in authors if a.affiliation_id is not None}
    if not affiliation_ids:
        return {}

    return {
        InstitutionId(pk): name
        for pk, name in Institution.objects.filter(pk__in=affiliation_ids).values_list("pk", "name")
    }
