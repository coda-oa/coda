"""Detail models for funding request queries.

These are view-optimized data structures that differ from domain models:
- Flatten complex object graphs
- Resolve IDs to names for display
- Contain only what the view needs

Copied from domain/fundingrequest/references.py as these were specifically
created for the detail view.
"""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from coda.domain.author import Role
from coda.domain.orcid import Orcid
from coda.domain.publication.links import Link


@dataclass
class ExternalFundingDetail:
    """External funding with organization name resolved."""

    organization: str
    project_id: str
    project_name: str


@dataclass
class AuthorDetail:
    """Author with affiliation name resolved."""

    name: str
    email: str
    affiliation: str
    role: Role
    orcid: Orcid | None


@dataclass
class CoveredByContractDetail:
    """Payment covered by contract."""

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
class IndividuallyPaidDetail:
    """Payment made individually (not via contract)."""

    url: str

    @property
    def status(self) -> str:
        return "Paid"

    @property
    def url_title(self) -> str:
        return "View Invoices"


@dataclass
class InvoiceReceivedDetail:
    """Invoice received but not yet fully paid."""

    url: str

    @property
    def status(self) -> str:
        return "Invoice received"

    @property
    def url_title(self) -> str:
        return "View Invoices"


@dataclass
class UnpaidDetail:
    """No payment received."""

    @property
    def status(self) -> str:
        return "Unpaid"


type PublicationPaymentDetail = (
    CoveredByContractDetail | IndividuallyPaidDetail | InvoiceReceivedDetail | UnpaidDetail
)


@dataclass(frozen=True)
class ContractYearDetail:
    """Detail model for ContractYear - flattens nested Contract object.

    Domain ContractYear contains entire Contract with publishers, journals,
    dates, etc. View only needs these 4 fields for display.
    """

    contract_id: int
    name: str
    year: int
    is_in_contract_period: bool


@dataclass(frozen=True)
class PublicationDetail:
    """Detail model for publication with all display data resolved.

    Resolves journal/publisher IDs to names and flattens contract object graphs.
    """

    # Basic metadata
    edit_url: str
    title: str
    request_remarks: str

    # Authors with institution names resolved
    relevant_authors: list[AuthorDetail]
    other_authors: list[str]

    # Publishing entity (journal OR publisher) with resolved names
    publishing_entity_type: Literal["Journal", "Publisher"]
    publishing_entity_name: str
    publishing_entity_identifier_name: str
    publishing_entity_identifier: str

    # Publication state
    publication_state: str
    online_publication_date: datetime.date | None
    print_publication_date: datetime.date | None

    # Vocabularies (already strings in domain)
    license: str
    publication_type: str
    subject_area: str
    oa_type: str

    # Links (domain Link works perfectly!)
    references: list[Link]

    # Contracts (using flattened ContractYearDetail!)
    contracts: list[ContractYearDetail]

    # Payment details
    payment_details: PublicationPaymentDetail


@dataclass(frozen=True)
class ReviewDetail:
    """Flattened review state for display."""

    value: str  # ReviewResult enum value string e.g. "open", "approved"
    remarks: str
    funding_amount: Any  # Money — kept as-is for template rendering


@dataclass(frozen=True)
class EstimatedCostDetail:
    """Flattened estimated cost for display."""

    amount: Any  # Money
    method: Any  # PaymentMethod enum — template uses .value


@dataclass(frozen=True)
class FundingRequestDetail:
    """Fully resolved detail model for the funding request detail view.

    Replaces passing the domain AnyFundingRequest into the template.
    All IDs resolved to names, all nested objects flattened to display values.
    """

    id: int
    request_id: str
    request_date: datetime.date
    review: ReviewDetail
    review_remarks: str  # convenience alias for review.remarks
    funding_amount: Any  # decided amount (Money) — template shortcut
    estimated_cost: EstimatedCostDetail
    external_costsplitting: bool
    publication: PublicationDetail
    external_funding: list[ExternalFundingDetail]
    updated_at: datetime.date
    labels: Iterable[Any]  # Django Label QuerySet (avoid circular import)
    edit_submitter_url: str
    edit_funding_url: str
    contact: Any  # FilledContact | NoContact — kept as-is for template rendering


@dataclass(frozen=True)
class FundingRequestListItem:
    """List item for funding request display.

    Optimized for list view - contains only what the template needs.
    Uses Django Label model directly (already prefetched in query).
    """

    type: Literal["Article", "Monograph"]
    id: int
    url: str
    request_id: str
    publication_title: str
    authors: list[str]  # Author names only (not full Author objects)
    publishing_entity_type: Literal["Journal", "Publisher"]
    publishing_entity_name: str
    publishing_entity_url: str
    updated_at: datetime.date
    labels: Iterable[Any]  # Django Label QuerySet (avoid circular import)
    status: str  # ReviewResult value
    payment_status: PublicationPaymentDetail
    publication_state: str
    # Article-specific fields (None for monographs)
    journal_publisher_name: str | None = None
    journal_publisher_url: str | None = None
    # Contract validation
    has_invalid_contract_years: bool = False
