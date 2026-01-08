"""Query functions for funding request detail view.

Function-based query service following CQRS-lite pattern:
- Read-side operations only
- Optimized DB queries with joins/prefetches
- Returns detail models where domain models are insufficient
- Returns domain models where they work fine
"""

import datetime
from collections.abc import Iterable
from typing import Any, Literal, cast
from urllib.parse import urlencode

from django.db import models
from django.urls import reverse

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import deserialize_role
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import checks as checks_service
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Publication as PublicationModel
from coda.apps.publications.services import publications as publication_service
from coda.apps.publishers.models import Publisher
from coda.domain.author import Role
from coda.domain.contract import ContractYear
from coda.domain.fundingrequest import ExternalFunding, FundingRequestId
from coda.domain.orcid import Orcid
from coda.domain.publication import BasePublication, Monograph, Publication
from coda.domain.publication.payment import (
    PublicationCoveredByContract,
    PublicationPaymentStatus,
)
from coda.domain.publication.publication import PublicationState, Published

from .models import (
    AuthorDetail,
    ContractYearDetail,
    CoveredByContractDetail,
    ExternalFundingDetail,
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
        .prefetch_related("labels")
        .get(pk=fr.id)
    )

    pub_model = PublicationModel.objects.prefetch_related(
        models.Prefetch(
            "relevant_authors",
            queryset=AuthorModel.objects.select_related("affiliation", "identifier"),
        )
    ).get(pk=fr.publication.id)

    external_funding_details = _build_external_funding_details(fr.external_funding)

    django_authors = cast(Any, pub_model).relevant_authors.all()
    publication_detail = _build_publication_detail(
        pub=fr.publication,
        django_authors=django_authors,
        fr_id=fr.id,
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
    }


def _build_external_funding_details(
    domain_fundings: Iterable[ExternalFunding],
) -> list[ExternalFundingDetail]:
    """Convert domain ExternalFunding to detail models with org names.

    Uses efficient bulk query to fetch organization names.

    Args:
        domain_fundings: Domain ExternalFunding with organization IDs

    Returns:
        List of ExternalFundingDetail with organization names resolved
    """
    fundings_list = list(domain_fundings)
    if not fundings_list:
        return []

    org_ids = [f.organization for f in fundings_list]
    orgs = FundingOrganization.objects.filter(id__in=org_ids).values("id", "name")
    org_map = {org["id"]: org["name"] for org in orgs}

    return [
        ExternalFundingDetail(
            organization=org_map.get(f.organization, f"Unknown ({f.organization})"),
            project_id=f.project_id,
            project_name=f.project_name,
        )
        for f in fundings_list
    ]


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


def _build_contract_year_details(
    contract_years: Iterable[ContractYear],
) -> list[ContractYearDetail]:
    """Convert domain ContractYear to ContractYearDetail.

    Flattens nested Contract object - view only needs 4 fields.

    Args:
        contract_years: Domain ContractYear objects

    Returns:
        List of ContractYearDetail with flattened data
    """
    return [
        ContractYearDetail(
            contract_id=cy.contract_id or 0,
            name=cy.name,
            year=cy.year,
            is_in_contract_period=cy.is_in_contract_period(),
        )
        for cy in contract_years
    ]


def _extract_publication_date(state: PublicationState) -> datetime.date | None:
    """Extract publication date from domain PublicationState."""
    if isinstance(state, Published):
        return state.online
    return None


def _get_publication_edit_url(pub: BasePublication, fr_id: FundingRequestId) -> str:
    """Get edit URL for publication based on type.

    Args:
        pub: Domain publication (Publication or Monograph)
        fr_id: Funding request ID for URL generation

    Returns:
        URL to edit the publication metadata for this funding request
    """
    if isinstance(pub, Publication):
        return reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})
    elif isinstance(pub, Monograph):
        return reverse("fundingrequests:update_monograph_meta", kwargs={"pk": fr_id})
    else:
        raise ValueError(f"Unknown publication type: {type(pub)}")


def _build_publishing_entity_info(
    pub: BasePublication,
) -> tuple[Literal["Journal", "Publisher"], str, str, str]:
    """Extract publishing entity info (journal OR publisher).

    Fetches journal/publisher from DB (1 query with select_related).

    Args:
        pub: Domain publication (Publication or Monograph)

    Returns:
        Tuple of (type, name, identifier_name, identifier)
    """
    if isinstance(pub, Publication):
        journal = Journal.objects.select_related("publisher").get(pk=pub.journal)
        return (
            "Journal",
            f"{journal.title}, {journal.publisher.name}",
            "EISSN",
            journal.eissn,
        )
    elif isinstance(pub, Monograph):
        publisher = Publisher.objects.get(pk=pub.publisher)
        return ("Publisher", publisher.name, "", "")
    else:
        raise ValueError(f"Unknown publication type: {type(pub)}")


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
    # Get edit URL
    edit_url = _get_publication_edit_url(pub, fr_id)
    author_details = _build_author_details(django_authors)

    entity_type, entity_name, identifier_name, identifier = _build_publishing_entity_info(pub)

    if pub.id is None:
        raise ValueError("Publication must have an ID")
    payment_status = publication_service.get_payment_status(pub.id)
    payment_details = _build_payment_details(payment_status, str(fr_id))

    publication_date = _extract_publication_date(pub.publication_state)
    contract_details = _build_contract_year_details(pub.contracts)

    return PublicationDetail(
        edit_url=edit_url,
        title=pub.title,
        request_remarks=request_remarks,
        relevant_authors=author_details,
        other_authors=list(pub.other_authors),
        publishing_entity_type=entity_type,
        publishing_entity_name=entity_name,
        publishing_entity_identifier_name=identifier_name,
        publishing_entity_identifier=identifier,
        publication_state=pub.publication_state.name(),
        publication_date=publication_date,
        license=pub.license.value,
        publication_type=pub.publication_type.name,
        subject_area=pub.subject_area.name,
        oa_type=pub.open_access_type.value,
        references=list(pub.links),
        contracts=contract_details,
        payment_details=payment_details,
    )
