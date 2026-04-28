"""View model mappers for funding request queries.

Convention: one mapper class per view model type defined in models.py.
Each mapper exposes a single `map()` classmethod that takes domain objects
or DTOs — with all DB-resolved data passed in as arguments — and returns
the corresponding view model.

Mappers are pure transformations: no DB access, no side effects.
Callers are responsible for fetching any data needed (institution names,
org names, journal/publisher names) before calling map().

ORM mappers (prefetch + ORM → domain) live in fundingrequests/mappers/.
These mappers handle the second step: domain/DTO → view model.

Usage:
    # Need a view model? Find or add its mapper class here.
    detail = PaymentDetailMapper.map(payment_status, request_id)
    author = AuthorDetailMapper.map(author, affiliation_names)
    pub = PublicationDetailMapper.map(pub, author_details, edit_url, remarks, payment,
                                      entity_type, entity_name, identifier_name, identifier)
"""

import datetime
from collections.abc import Iterable
from typing import Literal
from urllib.parse import urlencode

from django.urls import reverse

from coda.domain.author import Author, InstitutionId
from coda.domain.contract import ContractYear
from coda.domain.fundingrequest import ExternalFunding, FundingRequestId
from coda.domain.publication import BasePublication, Monograph, Publication
from coda.domain.publication.payment import PublicationCoveredByContract, PublicationPaymentStatus
from coda.domain.publication.publication import Published

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


class PaymentDetailMapper:
    """Maps domain PublicationPaymentStatus → PublicationPaymentDetail view model."""

    @staticmethod
    def map(status: PublicationPaymentStatus, request_id: str) -> PublicationPaymentDetail:
        if isinstance(status, PublicationCoveredByContract):
            return CoveredByContractDetail(
                contract_id=str(status.contract_id),
                contract_name=status.contract_name,
                contract_year=str(status.contract_year),
                url=reverse("contracts:detail", kwargs={"pk": status.contract_id}),
            )

        invoice_list_url = f"{reverse('invoices:list')}?{urlencode({'search_term': request_id})}"

        if not status.payments():
            return UnpaidDetail()
        if status.all_paid():
            return IndividuallyPaidDetail(url=invoice_list_url)
        if status.has_pending_payments():
            return InvoiceReceivedDetail(url=invoice_list_url)
        return UnpaidDetail()


class AuthorDetailMapper:
    """Maps domain Author → AuthorDetail view model.

    Caller is responsible for fetching affiliation_names before calling map().
    """

    @staticmethod
    def map(author: Author, affiliation_names: dict[InstitutionId, str]) -> AuthorDetail:
        return AuthorDetail(
            name=author.name,
            email=author.email,
            affiliation=affiliation_names.get(author.affiliation, "") if author.affiliation else "",
            role=author.role,
            orcid=author.orcid,
        )

    @classmethod
    def map_all(
        cls,
        authors: Iterable[Author],
        affiliation_names: dict[InstitutionId, str],
    ) -> list[AuthorDetail]:
        return [cls.map(a, affiliation_names) for a in authors]


class ContractYearDetailMapper:
    """Maps domain ContractYear → ContractYearDetail view model."""

    @staticmethod
    def map(contract_year: ContractYear) -> ContractYearDetail:
        return ContractYearDetail(
            contract_id=contract_year.contract_id or 0,
            name=contract_year.name,
            year=contract_year.year,
            is_in_contract_period=contract_year.is_in_contract_period(),
        )

    @classmethod
    def map_all(cls, contract_years: Iterable[ContractYear]) -> list[ContractYearDetail]:
        return [cls.map(cy) for cy in contract_years]


class ExternalFundingDetailMapper:
    """Maps domain ExternalFunding → ExternalFundingDetail view model.

    Caller is responsible for fetching org_names before calling map().
    """

    @staticmethod
    def map(funding: ExternalFunding, org_names: dict[int, str]) -> ExternalFundingDetail:
        return ExternalFundingDetail(
            organization=org_names.get(funding.organization, f"Unknown ({funding.organization})"),
            project_id=funding.project_id,
            project_name=funding.project_name,
        )

    @classmethod
    def map_all(
        cls, fundings: Iterable[ExternalFunding], org_names: dict[int, str]
    ) -> list[ExternalFundingDetail]:
        return [cls.map(f, org_names) for f in fundings]


class PublicationDetailMapper:
    """Maps domain BasePublication → PublicationDetail view model.

    Caller is responsible for resolving publishing entity info (journal/publisher
    names) and passing them in. No DB access inside map().
    """

    @staticmethod
    def map(
        pub: BasePublication,
        author_details: list[AuthorDetail],
        edit_url: str,
        request_remarks: str,
        payment_details: PublicationPaymentDetail,
        publishing_entity_type: Literal["Journal", "Publisher"],
        publishing_entity_name: str,
        publishing_entity_identifier_name: str,
        publishing_entity_identifier: str,
    ) -> PublicationDetail:
        publication_date: datetime.date | None = None
        if isinstance(pub.publication_state, Published):
            publication_date = pub.publication_state.online

        return PublicationDetail(
            edit_url=edit_url,
            title=pub.title,
            request_remarks=request_remarks,
            relevant_authors=author_details,
            other_authors=list(pub.other_authors),
            publishing_entity_type=publishing_entity_type,
            publishing_entity_name=publishing_entity_name,
            publishing_entity_identifier_name=publishing_entity_identifier_name,
            publishing_entity_identifier=publishing_entity_identifier,
            publication_state=pub.publication_state.name(),
            publication_date=publication_date,
            license=pub.license.value,
            publication_type=pub.publication_type.name,
            subject_area=pub.subject_area.name,
            oa_type=pub.open_access_type.value,
            references=list(pub.links),
            contracts=ContractYearDetailMapper.map_all(pub.contracts),
            payment_details=payment_details,
        )

    @staticmethod
    def get_edit_url(pub: BasePublication, fr_id: FundingRequestId | None) -> str:
        """Derive the edit URL for a publication based on its type (no DB access)."""
        if fr_id is None:
            return "#edit-publication-preview"
        if isinstance(pub, Publication):
            return reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})
        elif isinstance(pub, Monograph):
            return reverse("fundingrequests:update_monograph_meta", kwargs={"pk": fr_id})
        else:
            raise ValueError(f"Unknown publication type: {type(pub)}")
