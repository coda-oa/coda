import datetime
from collections.abc import Iterable
from dataclasses import dataclass

from coda.domain.author import Role
from coda.domain.contract import ContractYear
from coda.domain.fundingrequest import Payment, Review
from coda.domain.orcid import Orcid
from coda.domain.publication.links import Link


@dataclass
class FundingRequestReference:
    request_id: str
    url: str


@dataclass
class Label:
    id: int
    name: str
    color: str

    def __str__(self) -> str:
        return self.name


@dataclass
class ExternalFundingDetails:
    organization: str
    project_id: str
    project_name: str


@dataclass
class AuthorDetails:
    name: str
    email: str
    affiliation: str
    role: Role
    orcid: Orcid | None


@dataclass
class CoveredByContractDetails:
    contract_id: str
    contract_name: str
    contract_year: str
    url: str

    @property
    def status(self) -> str:
        return "Covered by contract"

    @property
    def url_title(self) -> str:
        return f"Contract: {self.contract_name} ({self.contract_year})"


@dataclass
class IndividuallyPaidDetails:
    url: str

    @property
    def status(self) -> str:
        return "Paid"

    @property
    def url_title(self) -> str:
        return "View Invoices"


@dataclass
class InvoiceReceivedDetails:
    url: str

    @property
    def status(self) -> str:
        return "Invoice received"

    @property
    def url_title(self) -> str:
        return "View Invoices"


@dataclass
class UnpaidDetails:
    @property
    def status(self) -> str:
        return "Unpaid"


type PublicationPaymentDetails = (
    CoveredByContractDetails | IndividuallyPaidDetails | InvoiceReceivedDetails | UnpaidDetails
)


@dataclass
class PublicationDetails:
    edit_url: str
    title: str
    relevant_authors: list[AuthorDetails]
    other_authors: Iterable[str]
    publishing_entity_type: str
    publishing_entity_name: str
    publishing_entity_identifier_name: str
    publishing_entity_identifier: str
    publication_state: str
    publication_date: datetime.date | None
    license: str
    publication_type: str
    subject_area: str
    oa_type: str
    references: Iterable[Link]
    contracts: Iterable[ContractYear]
    payment_details: PublicationPaymentDetails
    request_remarks: str = ""


@dataclass
class FundingRequestDetails:
    id: int
    request_id: str
    labels: Iterable[Label]
    request_date: datetime.date
    updated_at: datetime.date
    payment: Payment
    review_status: Review
