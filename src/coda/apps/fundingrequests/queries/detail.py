"""Query functions for funding request detail view.

Function-based query service following CQRS-lite pattern:
- Read-side operations only
- Optimized DB queries with joins/prefetches
- Returns detail models where domain models are insufficient
- Returns domain models where they work fine
"""

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode

from django.db.models import Prefetch
from django.urls import reverse

from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.mappers import FundingRequestDetailMapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.services import publications as publication_service
from coda.contexts.fundingrequest.services import checks as checks_service
from coda.domain.author import Author, InstitutionId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.publication import BasePublication
from coda.domain.publication.payment import (
    PublicationCoveredByContract,
    PublicationPaymentStatus,
)

from .builders import (
    build_external_funding_details,
    build_publication_detail_from_domain,
    get_publication_edit_url,
)
from .models import (
    AuthorDetail,
    CoveredByContractDetail,
    IndividuallyPaidDetail,
    InvoiceReceivedDetail,
    PublicationDetail,
    PublicationPaymentDetail,
    UnpaidDetail,
)


def get_detail_context(fr_id: FundingRequestId) -> dict[str, Any]:
    """Get complete context for funding request detail view.

    Orchestrates all queries efficiently:
    1. Fetch Django model with for_detail() — single query covering domain
       hydration AND display-only fields (labels, updated_at)
    2. Map to domain object via mapper
    3. Build detail models where needed
    4. Return complete context dict

    Args:
        fr_id: Funding request ID

    Returns:
        Context dict for template with mix of domain models and detail models
    """
    fr_model = FundingRequestDetailMapper.prefetch(FundingRequestModel.objects.all()).get(pk=fr_id)
    fr = FundingRequestDetailMapper.map(fr_model)

    if fr.id is None:
        raise ValueError("Cannot create context for unsaved FundingRequest")
    if fr.publication.id is None:
        raise ValueError("Cannot create context for FundingRequest with unsaved Publication")

    external_funding_details = build_external_funding_details(fr.external_funding)

    publication_detail = _build_publication_detail(
        pub=fr.publication,
        fr_id=fr.id,
        request_id=str(fr.request_id),
        request_remarks=fr.request_remarks,
    )

    checkrun = checks_service.get_checkrun(fr.id)

    return {
        "funding_request": fr,
        "publication": publication_detail,
        "contact": fr.extra_contact,
        "external_funding": external_funding_details,
        "updated_at": fr_model.updated_at.date(),
        "labels": fr_model.labels.all(),
        "label_form": ChooseLabelForm(),
        "checks": checkrun,
        # Edit URLs for partials
        "edit_submitter_url": reverse("fundingrequests:update_submitter", kwargs={"pk": fr.id}),
        "edit_funding_url": reverse("fundingrequests:update_funding", kwargs={"pk": fr.id}),
    }


def _fetch_affiliation_names(
    authors: Iterable[Author],
) -> dict[InstitutionId, str]:
    """Bulk-fetch institution names for a set of authors.

    Single query regardless of number of authors.

    Args:
        authors: Domain Author objects whose affiliation IDs to resolve

    Returns:
        Mapping of InstitutionId → institution name. Empty dict if no affiliations.
    """
    # Local import to avoid circular dependency between fundingrequests and institutions apps
    from coda.apps.institutions.models import Institution

    affiliation_ids = {a.affiliation for a in authors if a.affiliation is not None}
    if not affiliation_ids:
        return {}

    return {
        InstitutionId(pk): name
        for pk, name in Institution.objects.filter(pk__in=affiliation_ids).values_list("pk", "name")
    }


def _build_author_details(
    authors: Iterable[Author],
    affiliation_names: dict[InstitutionId, str],
) -> list[AuthorDetail]:
    """Convert domain Author objects to AuthorDetail.

    Args:
        authors: Domain Author objects (already loaded on publication)
        affiliation_names: Pre-fetched mapping of InstitutionId → name

    Returns:
        List of AuthorDetail with institution names resolved
    """
    return [
        AuthorDetail(
            name=author.name,
            email=author.email,
            affiliation=affiliation_names.get(author.affiliation, "") if author.affiliation else "",
            role=author.role,
            orcid=author.orcid,
        )
        for author in authors
    ]


def _build_payment_details(
    payment_status: PublicationPaymentStatus, request_id: str
) -> PublicationPaymentDetail:
    """Build payment details from payment status.

    Args:
        payment_status: Domain payment status
        request_id: Funding request ID for invoice URL

    Returns:
        Appropriate payment detail model based on status
    """
    if isinstance(payment_status, PublicationCoveredByContract):
        return CoveredByContractDetail(
            contract_id=str(payment_status.contract_id),
            contract_name=payment_status.contract_name,
            contract_year=str(payment_status.contract_year),
            url=reverse("contracts:detail", kwargs={"pk": payment_status.contract_id}),
        )

    invoice_list_url = f"{reverse('invoices:list')}?{urlencode({'search_term': request_id})}"

    if not payment_status.payments():
        return UnpaidDetail()

    if payment_status.all_paid():
        return IndividuallyPaidDetail(url=invoice_list_url)

    if payment_status.has_pending_payments():
        return InvoiceReceivedDetail(url=invoice_list_url)

    return UnpaidDetail()


def _build_publication_detail(
    pub: BasePublication,
    fr_id: FundingRequestId,
    request_id: str,
    request_remarks: str,
) -> PublicationDetail:
    """Build PublicationDetail with all resolved names.

    Authors and affiliation names are derived from the domain publication
    object — no additional Django model queries needed.

    Args:
        pub: Domain publication with pre-loaded authors
        fr_id: Funding request ID for URL generation
        request_id: Funding request string ID for invoice URLs
        request_remarks: Request remarks

    Returns:
        PublicationDetail with all display data resolved
    """
    edit_url = get_publication_edit_url(pub, fr_id)
    affiliation_names = _fetch_affiliation_names(pub.relevant_authors)
    author_details = _build_author_details(pub.relevant_authors, affiliation_names)

    if pub.id is None:
        raise ValueError("Publication must have an ID")
    payment_status = publication_service.get_payment_status(pub.id)
    payment_details = _build_payment_details(payment_status, request_id)

    return build_publication_detail_from_domain(
        pub=pub,
        author_details=author_details,
        edit_url=edit_url,
        request_remarks=request_remarks,
        payment_details=payment_details,
    )
