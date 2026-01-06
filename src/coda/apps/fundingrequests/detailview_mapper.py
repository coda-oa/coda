"""Mapper functions for FundingRequest detail view models.

Maps Django ORM models to domain detail classes for use in detail views.
"""

from collections.abc import Iterable
from typing import Literal, TypedDict
from urllib.parse import urlencode

from django.urls import reverse

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import deserialize_role
from coda.apps.contracts import mapper as contract_mapper
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import FundingRequestReview
from coda.apps.fundingrequests.models import Label as LabelModel
from coda.apps.publications.models import AttachedContract
from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.services import publications
from coda.domain.author import Role
from coda.domain.contract import ContractYear
from coda.domain.fundingrequest import Payment, PaymentMethod, Review
from coda.domain.fundingrequest.references import (
    AuthorDetails,
    CoveredByContractDetails,
    ExternalFundingDetails,
    FundingRequestDetails,
    IndividuallyPaidDetails,
    InvoiceReceivedDetails,
    Label,
    PublicationDetails,
    PublicationPaymentDetails,
    UnpaidDetails,
)
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.orcid import Orcid
from coda.domain.publication import License, Link, OpenAccessType
from coda.domain.publication import links as link_factory
from coda.domain.publication.payment import (
    PublicationCoveredByContract,
    PublicationPayments,
    PublicationPaymentStatus,
)
from coda.domain.publication.publication import PublicationId


class PublishingEntityInfo(TypedDict):
    """Publishing entity details extracted from funding request."""

    edit_url: str
    name: str
    identifier_name: str
    identifier: str
    type: Literal["Journal", "Publisher"]


def to_funding_request_details(fr: FundingRequestModel) -> FundingRequestDetails:
    """Convert Django FundingRequest model to FundingRequestDetails."""
    return FundingRequestDetails(
        id=fr.pk,
        request_id=fr.request_id,
        labels=_to_labels(fr.labels.all()),
        request_date=fr.request_date,
        updated_at=fr.updated_at.date(),
        payment=_to_payment(fr),
        review_status=_to_review(fr.review),
        external_costsplitting=fr.external_costsplitting,
    )


def to_publication_details(fr: FundingRequestModel) -> PublicationDetails:
    """Convert publication from FundingRequest to PublicationDetails."""
    publication = fr.publication
    entity_info = _extract_publishing_entity_info(fr)

    payment_status = publications.get_payment_status(PublicationId(publication.id))
    payment_details = to_payment_details(payment_status, fr.request_id)

    return PublicationDetails(
        edit_url=entity_info["edit_url"],
        title=publication.title,
        relevant_authors=_to_author_list(publication.relevant_authors.all()),
        other_authors=publication.authors,
        publishing_entity_type=entity_info["type"],
        publishing_entity_name=entity_info["name"],
        publishing_entity_identifier_name=entity_info["identifier_name"],
        publishing_entity_identifier=entity_info["identifier"],
        publication_state=publication.publication_state,
        publication_date=publication.online_publication_date,
        license=License[publication.license].value,
        publication_type=publication.publication_type.name,
        subject_area=publication.subject_area.name,
        oa_type=OpenAccessType[publication.open_access_type].value,
        references=_to_links(publication.links.all()),
        contracts=_to_contracts(publication.attached_contracts.all()),
        payment_details=payment_details,
        request_remarks=fr.request_remarks,
    )


def to_payment_details(
    payment_status: PublicationPaymentStatus, request_id: str
) -> PublicationPaymentDetails:
    """Convert PublicationPaymentStatus to appropriate PublicationPaymentDetails."""
    if isinstance(payment_status, PublicationCoveredByContract):
        return _to_contract_covered_details(payment_status)

    return _to_individual_payment_details(payment_status, request_id)


def to_external_funding_list(
    external_funding: Iterable[ExternalFundingModel],
) -> list[ExternalFundingDetails]:
    """Convert list of ExternalFunding models to ExternalFundingDetails."""
    return [_to_external_funding_details(ef) for ef in external_funding]


# ============================================================================
# PRIVATE CONVERSIONS
# ============================================================================


def _to_external_funding_details(ef: ExternalFundingModel) -> ExternalFundingDetails:
    return ExternalFundingDetails(
        organization=ef.organization.name,
        project_id=ef.project_id,
        project_name=ef.project_name,
    )


def _to_author_details(author_model: AuthorModel) -> AuthorDetails:
    """Convert Django Author model to AuthorDetails."""
    orcid = None
    if author_model.identifier and author_model.identifier.orcid:
        orcid = Orcid(author_model.identifier.orcid)

    role = deserialize_role(author_model.roles) if author_model.roles else Role.CO_AUTHOR

    return AuthorDetails(
        name=author_model.name,
        email=author_model.email or "",
        affiliation=author_model.affiliation.name if author_model.affiliation else "",
        role=role,
        orcid=orcid,
    )


def _to_author_list(authors: Iterable[AuthorModel]) -> list[AuthorDetails]:
    return [_to_author_details(author) for author in authors]


def _to_contracts(attached_contracts: Iterable[AttachedContract]) -> Iterable[ContractYear]:
    """Convert AttachedContract models to ContractYear domain objects."""
    return [
        contract_mapper.as_domain_object(ac.contract).in_year(ac.contract_year)
        for ac in attached_contracts
    ]


def _to_contract_covered_details(
    payment_status: PublicationCoveredByContract,
) -> CoveredByContractDetails:
    """Convert contract-covered payment status to details."""
    return CoveredByContractDetails(
        contract_id=str(payment_status.contract_id),
        contract_name=payment_status.contract_name,
        contract_year=str(payment_status.contract_year),
        url=reverse("contracts:detail", kwargs={"pk": payment_status.contract_id}),
    )


def _to_individual_payment_details(
    payment_status: PublicationPayments, request_id: str
) -> PublicationPaymentDetails:
    """Convert individual payment status to appropriate details type."""
    invoice_list_url = f"{reverse('invoices:list')}?{urlencode({'search_term': request_id})}"

    if not payment_status.payments():
        return UnpaidDetails()

    if payment_status.all_paid():
        return IndividuallyPaidDetails(url=invoice_list_url)

    if payment_status.has_pending_payments():
        return InvoiceReceivedDetails(url=invoice_list_url)

    return UnpaidDetails()


def _to_labels(labels: Iterable[LabelModel]) -> Iterable[Label]:
    return [Label(id=label.pk, name=label.name, color=label.hexcolor) for label in labels]


def _to_links(link_models: Iterable[LinkModel]) -> Iterable[Link]:
    return [link_factory.create_link(link.type.name, link.value) for link in link_models]


def _to_payment(fr: FundingRequestModel) -> Payment:
    return Payment(
        amount=Money(fr.estimated_cost, Currency[fr.estimated_cost_currency]),
        method=PaymentMethod(fr.payment_method),
    )


def _to_review(review_model: FundingRequestReview) -> Review:
    return Review(
        decided_funding=Money(
            review_model.decided_funding_amount or 0,
            Currency.from_code(review_model.decided_funding_currency or "EUR"),
        ),
        result=ReviewResult.of(review_model.review_result),
        remarks=review_model.remarks,
    )


def _extract_publishing_entity_info(fr: FundingRequestModel) -> PublishingEntityInfo:
    """Extract publishing entity information based on article/monograph type.

    Determines whether the publication is a journal article or monograph,
    then extracts the appropriate entity details including edit URL.
    """
    publication = fr.publication
    article_journal = publication.article_journal
    monograph_publisher = publication.monograph_publisher

    if article_journal is not None:
        return {
            "edit_url": reverse("fundingrequests:update_publication", kwargs={"pk": fr.pk}),
            "name": f"{article_journal.title}, {article_journal.publisher.name}",
            "identifier_name": "EISSN",
            "identifier": article_journal.eissn,
            "type": "Journal",
        }
    elif monograph_publisher is not None:
        return {
            "edit_url": reverse("fundingrequests:update_monograph_meta", kwargs={"pk": fr.pk}),
            "name": monograph_publisher.name,
            "identifier_name": "",
            "identifier": "",
            "type": "Publisher",
        }
    else:
        raise ValueError("Publication is neither an article nor a monograph")
