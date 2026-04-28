"""Query functions for funding request detail view.

Function-based query service following CQRS-lite pattern:
- Read-side operations only
- Optimized DB queries with joins/prefetches
- Returns detail models where domain models are insufficient
- Returns domain models where they work fine
"""

from typing import Any, Literal

from django.db.models import Prefetch
from django.urls import reverse

from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.mappers import FundingRequestDetailMapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.publications.services import publications as publication_service
from coda.contexts.fundingrequest.services import checks as checks_service
from coda.domain.author import Author, InstitutionId
from coda.domain.fundingrequest import ExternalFunding, FundingRequestId
from coda.domain.publication import BasePublication, Monograph, Publication

from .mappers import (
    AuthorDetailMapper,
    ExternalFundingDetailMapper,
    PaymentDetailMapper,
    PublicationDetailMapper,
)


def get_detail_context(fr_id: FundingRequestId) -> dict[str, Any]:
    """Get complete context for funding request detail view.

    Orchestrates all queries efficiently:
    1. Fetch Django model with prefetch — single query covering domain
       hydration AND display-only fields (labels, updated_at)
    2. Map to domain object via mapper
    3. Fetch supporting data (affiliations, org names, publishing entity)
    4. Build detail models via view model mappers
    5. Return complete context dict

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

    # Fetch supporting data
    affiliation_names = _fetch_affiliation_names(list(fr.publication.relevant_authors))
    org_names = _fetch_org_names(list(fr.external_funding))
    entity_type, entity_name, identifier_name, identifier = _fetch_publishing_entity(fr.publication)
    payment_status = publication_service.get_payment_status(fr.publication.id)

    # Build view models
    author_details = AuthorDetailMapper.map_all(fr.publication.relevant_authors, affiliation_names)
    payment_details = PaymentDetailMapper.map(payment_status, str(fr.request_id))
    external_funding_details = ExternalFundingDetailMapper.map_all(fr.external_funding, org_names)
    publication_detail = PublicationDetailMapper.map(
        pub=fr.publication,
        author_details=author_details,
        edit_url=PublicationDetailMapper.get_edit_url(fr.publication, fr.id),
        request_remarks=fr.request_remarks,
        payment_details=payment_details,
        publishing_entity_type=entity_type,
        publishing_entity_name=entity_name,
        publishing_entity_identifier_name=identifier_name,
        publishing_entity_identifier=identifier,
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
        "edit_submitter_url": reverse("fundingrequests:update_submitter", kwargs={"pk": fr.id}),
        "edit_funding_url": reverse("fundingrequests:update_funding", kwargs={"pk": fr.id}),
    }


# ============================================================================
# PRIVATE QUERY HELPERS
# ============================================================================


def _fetch_affiliation_names(authors: list[Author]) -> dict[InstitutionId, str]:
    """Bulk-fetch institution names for a set of authors (single query)."""
    # Local import to avoid circular dependency between fundingrequests and institutions apps
    from coda.apps.institutions.models import Institution

    affiliation_ids = {a.affiliation for a in authors if a.affiliation is not None}
    if not affiliation_ids:
        return {}

    return {
        InstitutionId(pk): name
        for pk, name in Institution.objects.filter(pk__in=affiliation_ids).values_list("pk", "name")
    }


def _fetch_org_names(fundings: list[ExternalFunding]) -> dict[int, str]:
    """Bulk-fetch funding organization names (single query)."""
    from coda.apps.fundingrequests.models import FundingOrganization

    if not fundings:
        return {}

    org_ids = [f.organization for f in fundings]
    return {
        org["id"]: org["name"]
        for org in FundingOrganization.objects.filter(id__in=org_ids).values("id", "name")
    }


def _fetch_publishing_entity(
    pub: BasePublication,
) -> tuple[Literal["Journal", "Publisher"], str, str, str]:
    """Fetch publishing entity display info from DB (single query)."""
    from coda.apps.journals.models import Journal
    from coda.apps.publishers.models import Publisher

    if isinstance(pub, Publication):
        journal = Journal.objects.select_related("publisher").get(pk=pub.journal)
        return ("Journal", f"{journal.title}, {journal.publisher.name}", "EISSN", journal.eissn)
    elif isinstance(pub, Monograph):
        publisher = Publisher.objects.get(pk=pub.publisher)
        return ("Publisher", publisher.name, "", "")
    else:
        raise ValueError(f"Unknown publication type: {type(pub)}")
