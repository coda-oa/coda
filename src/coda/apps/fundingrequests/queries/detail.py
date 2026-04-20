"""Query functions for funding request detail view.

Function-based query service following CQRS-lite pattern:
- Read-side operations only
- Optimized DB queries with joins/prefetches
- Returns detail models where domain models are insufficient
- Returns domain models where they work fine
"""

from collections.abc import Iterable
from typing import Any, cast
from urllib.parse import urlencode

from django.db import models
from django.db.models import Prefetch
from django.urls import reverse

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import deserialize_role
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.models import Publication as PublicationModel
from coda.apps.publications.services import publications as publication_service
from coda.contexts.fundingrequest.services import checks as checks_service
from coda.domain.author import Role
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.orcid import Orcid
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
    1. Fetch domain model from repository (with contracts)
    2. Fetch Django models with optimal joins/prefetches
    3. Build detail models where needed
    4. Return complete context dict

    Total queries: ~4-6 optimized queries

    Args:
        fr_id: Funding request ID

    Returns:
        Context dict for template with mix of domain models and detail models
    """
    fr = repository.get_by_id(fr_id)

    if fr.id is None:
        raise ValueError("Cannot create context for unsaved FundingRequest")
    if fr.publication.id is None:
        raise ValueError("Cannot create context for FundingRequest with unsaved Publication")

    fr_model = (
        FundingRequestModel.objects.select_related("extra_contact", "review")
        .prefetch_related(Prefetch("labels", queryset=Label.objects.order_by("name")))
        .get(pk=fr.id)
    )

    pub_model = PublicationModel.objects.prefetch_related(
        models.Prefetch(
            "relevant_authors",
            queryset=AuthorModel.objects.select_related("affiliation", "identifier"),
        )
    ).get(pk=fr.publication.id)

    external_funding_details = build_external_funding_details(fr.external_funding)

    django_authors = cast(Any, pub_model).relevant_authors.all()
    publication_detail = _build_publication_detail(
        pub=fr.publication,
        django_authors=django_authors,
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


def _build_author_details(
    django_authors: Iterable[AuthorModel],
) -> list[AuthorDetail]:
    """Convert Django Author models to AuthorDetail.

    Expects authors to be prefetched with select_related('affiliation', 'identifier').
    Uses already-loaded data - no additional queries.

    Args:
        django_authors: Django Author queryset with prefetched relationships

    Returns:
        List of AuthorDetail with institution names resolved
    """
    result = []
    for author_model in django_authors:
        orcid = None
        if author_model.identifier and author_model.identifier.orcid:
            orcid = Orcid(author_model.identifier.orcid)

        role = deserialize_role(author_model.roles) if author_model.roles else Role.CO_AUTHOR

        result.append(
            AuthorDetail(
                name=author_model.name,
                email=author_model.email or "",
                affiliation=author_model.affiliation.name if author_model.affiliation else "",
                role=role,
                orcid=orcid,
            )
        )
    return result


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
    django_authors: Iterable[AuthorModel],
    fr_id: FundingRequestId,
    request_id: str,
    request_remarks: str,
) -> PublicationDetail:
    """Build PublicationDetail with all resolved names.

    Args:
        pub: Domain publication with pre-loaded contracts
        django_authors: Django authors with select_related('affiliation', 'identifier')
        fr_id: Funding request ID for URL generation
        request_remarks: Request remarks

    Returns:
        PublicationDetail with all display data resolved
    """
    # Build view-specific data
    edit_url = get_publication_edit_url(pub, fr_id)
    author_details = _build_author_details(django_authors)

    if pub.id is None:
        raise ValueError("Publication must have an ID")
    payment_status = publication_service.get_payment_status(pub.id)
    payment_details = _build_payment_details(payment_status, request_id)

    # Use shared builder for core publication detail
    return build_publication_detail_from_domain(
        pub=pub,
        author_details=author_details,
        edit_url=edit_url,
        request_remarks=request_remarks,
        payment_details=payment_details,
    )
