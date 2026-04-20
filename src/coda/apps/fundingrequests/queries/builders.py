"""Shared builders for funding request detail models.

These functions convert domain objects to detail models for template rendering.
They are shared between regular detail view and DOI import preview.
"""

import datetime
from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal

from django.urls import reverse

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.domain.contract import ContractYear
from coda.domain.fundingrequest import ExternalFunding
from coda.domain.publication import BasePublication, Monograph, Publication
from coda.domain.publication.publication import PublicationState, Published

from .models import ContractYearDetail, ExternalFundingDetail, PublicationDetail

if TYPE_CHECKING:
    from .models import AuthorDetail, PublicationPaymentDetail


def build_external_funding_details(
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


def build_contract_year_details(
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


def extract_publication_dates(
    state: PublicationState,
) -> tuple[datetime.date | None, datetime.date | None]:
    """Extract online and print publication dates from domain PublicationState.

    Returns:
        Tuple of (online_date, print_date)
    """
    if isinstance(state, Published):
        return (state.online, state.print)
    return (None, None)


def get_publication_edit_url(pub: BasePublication, fr_id: int | None) -> str:
    """Get edit URL for publication based on type.

    Args:
        pub: Domain publication (Publication or Monograph)
        fr_id: Funding request ID for URL generation (None for preview)

    Returns:
        URL to edit the publication metadata for this funding request
    """
    if fr_id is None:
        # Preview mode - return placeholder
        return "#edit-publication-preview"

    if isinstance(pub, Publication):
        return reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})
    elif isinstance(pub, Monograph):
        return reverse("fundingrequests:update_monograph_meta", kwargs={"pk": fr_id})
    else:
        raise ValueError(f"Unknown publication type: {type(pub)}")


def build_publishing_entity_info(
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


def build_publication_detail_from_domain(
    pub: BasePublication,
    author_details: list["AuthorDetail"],
    edit_url: str,
    request_remarks: str,
    payment_details: "PublicationPaymentDetail",
) -> PublicationDetail:
    """Build PublicationDetail from domain publication.

    This is the shared core logic for building publication details.
    Caller is responsible for:
    - Converting authors to AuthorDetail
    - Generating appropriate edit URL
    - Providing payment details

    Args:
        pub: Domain publication with pre-loaded contracts
        author_details: List of AuthorDetail (already converted)
        edit_url: Edit URL for this publication
        request_remarks: Request remarks text
        payment_details: Payment details model

    Returns:
        PublicationDetail with all display data resolved
    """
    entity_type, entity_name, identifier_name, identifier = build_publishing_entity_info(pub)
    online_date, print_date = extract_publication_dates(pub.publication_state)
    contract_details = build_contract_year_details(pub.contracts)

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
        online_publication_date=online_date,
        print_publication_date=print_date,
        license=pub.license.value,
        publication_type=pub.publication_type.name,
        subject_area=pub.subject_area.name,
        oa_type=pub.open_access_type.value,
        references=list(pub.links),
        contracts=contract_details,
        payment_details=payment_details,
    )
