"""Import DTOs for fundingrequest import workflow.

This module consolidates all Pydantic DTOs used for JSON import validation.
DTOs are organized by entity type for clarity.

Field and class descriptions become part of the generated JSON schema
(shown and downloadable on the funding request import page), so keep them
accurate when changing import behavior.
"""

import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    PlainValidator,
    PositiveInt,
    ValidationError,
    WithJsonSchema,
    model_validator,
)

from coda.domain import issn, orcid
from coda.domain.author import Role
from coda.domain.fundingrequest import PaymentMethod, ReviewResult
from coda.domain.publication import License, OpenAccessType, links

# === Custom validators ===


def _valid_link_type(v: str) -> str:
    if not links.valid_link_type(v):
        raise ValueError(f"Link type '{v}' is not valid")
    return v


def _maybe_issn(v: str) -> str:
    if v == "":
        return v

    return issn.Issn(v)


LinkType = Annotated[str, PlainValidator(_valid_link_type), WithJsonSchema({"type": "string"})]
MaybeIssn = Annotated[str, PlainValidator(_maybe_issn), WithJsonSchema({"type": "string"})]
Orcid = Annotated[str, PlainValidator(orcid.Orcid), WithJsonSchema({"type": "string"})]


# === Author DTOs ===


class AuthorImportDto(BaseModel):
    """Author of the publication."""

    name: str = Field(description="Full name of the author.")
    email: str = Field(description="Contact email address of the author.")
    orcid: Orcid | None = Field(
        default=None, description="ORCID identifier (e.g. 0000-0001-2345-6789)."
    )
    affiliation: str | None = Field(
        default=None,
        description="Institutional affiliation by name; creates an institution entry if it does not exist.",
    )
    affiliation_internal_id: str | None = Field(
        default=None,
        description="Internal ID of an existing institution, as used by the institution structure export.",
    )
    role: Role = Field(
        default=Role.CO_AUTHOR,
        description="Role of the author in the publication: Submitter, Co-author, "
        "Corresponding author, or Submitting corresponding author.",
    )


# === Contract DTOs ===


class ContractImportDto(BaseModel):
    """Association of the publication with an existing contract."""

    name: str = Field(description="Contract name; the contract must already exist.")
    year: PositiveInt = Field(description="Contract year.")


# === Vocabulary DTOs ===


class ConceptImportDto(BaseModel):
    """Reference to a concept of a configurable vocabulary (e.g. COAR publication types, DFG subject areas)."""

    name: str = Field(default="", description="Concept name.")
    vocabulary_name: str = Field(
        default="", description="Name of the vocabulary the concept belongs to."
    )
    concept_id: str = Field(
        default="",
        description="Stable concept ID within the vocabulary; takes precedence over the name when set.",
    )


# === Review DTOs ===


class DecidedFundingImportDto(BaseModel):
    """Decided funding amount from the review process; may differ from the estimated cost if negotiation occurred."""

    amount: Decimal = Field(description="Approved funding amount.")
    currency: str = Field(description="Three-letter currency code (e.g. EUR, USD).")

    @classmethod
    def default(cls) -> "DecidedFundingImportDto":
        return cls(amount=Decimal("0.00"), currency="EUR")


class ReviewImportDto(BaseModel):
    """Review decision; imported requests bypass automated checks (DOAJ, blocklist)."""

    result: ReviewResult = Field(
        default=ReviewResult.Open,
        description="Review result: open, approved, rejected, waived, or closed.",
    )
    funding: DecidedFundingImportDto = Field(
        default_factory=DecidedFundingImportDto.default,
        description="Decided funding amount and currency.",
    )
    remarks: str = Field(default="", description="Reviewer remarks.")


# === Publication DTOs ===


PublishingStateOptions = Literal["unknown", "submitted", "accepted", "rejected", "published"]


class LinkImportDto(BaseModel):
    """Persistent identifier or link related to the publication (e.g. DOI, PMC, ISBN, Handle)."""

    type: LinkType = Field(
        description="Link type as configured in CODA (e.g. doi, isbn, pmc, handle)."
    )
    value: str = Field(description="Link value, e.g. the DOI itself.")


class PublishingStateImportDto(BaseModel):
    """Publication status and publication dates."""

    state: PublishingStateOptions = Field(
        default="unknown",
        description="Publication state: unknown, submitted, accepted, rejected, or published.",
    )
    online_date: datetime.date | None = Field(
        default=None, description="Online publication date (YYYY-MM-DD)."
    )
    print_date: datetime.date | None = Field(
        default=None, description="Print publication date (YYYY-MM-DD)."
    )


class PublicationImportDto(BaseModel):
    """Publication metadata of the funding request."""

    title: str = Field(description="Publication title.")
    kind: Literal["article", "monograph"] = Field(
        description="Publication kind; articles require an eissn, monographs require a publisher_name."
    )
    eissn: MaybeIssn = Field(
        default="",
        description="Electronic ISSN of the journal; required for articles, ignored for monographs.",
    )
    journal_name: str = Field(
        default="Imported nameless journal",
        description="Journal title; creates a journal if none exists with this E-ISSN.",
    )
    publisher_name: str = Field(
        default="Imported nameless publisher",
        description="Publisher name; creates the publisher if it does not exist.",
    )
    authors: list[AuthorImportDto] = Field(
        default_factory=list, description="Authors of the publication."
    )
    license: License = Field(
        default=License.Unknown,
        description="Open access license (e.g. CC-BY, CC0, Unknown, None).",
    )
    publishing_state: PublishingStateImportDto = Field(
        default_factory=PublishingStateImportDto,
        description="Publication status and publication dates.",
    )
    open_access_type: OpenAccessType = Field(
        description="Open access type: Gold, Diamond, Hybrid, Opt-in, Opt-out, Unknown, or Closed."
    )
    links: list[LinkImportDto] = Field(
        default_factory=list,
        description="Identifiers and links (DOI, PMC, ISBN, Handle, ...).",
    )
    contracts: list[ContractImportDto] = Field(
        default_factory=list, description="Contracts covering this publication."
    )
    subject_area: ConceptImportDto = Field(
        default_factory=ConceptImportDto,
        description="Subject area from a configured vocabulary (default: DFG Subject Classification).",
    )
    publication_type: ConceptImportDto = Field(
        default_factory=ConceptImportDto,
        description="Publication type from a configured vocabulary (default: COAR Resource Types 3.1).",
    )

    @model_validator(mode="after")
    def verify_eissn(self) -> Self:
        if self.kind == "article" and self.eissn == "":
            raise ValidationError("EISSN must be provided for articles")

        return self


# === FundingRequest DTOs ===


class ResearchFundingImportDto(BaseModel):
    """Third-party funding for the publication (e.g. DFG, BMBF)."""

    funder: str = Field(
        description="Funding organization name; creates the funder if it does not exist."
    )
    project_id: str = Field(description="Grant or project identifier.")
    project_name: str = Field(default="", description="Full project name.")


class CostEstimateImportDto(BaseModel):
    """Estimated publication costs; final costs are usually only known after invoicing."""

    amount: Decimal = Field(description="Estimated cost amount.")
    currency: str = Field(description="Three-letter currency code (e.g. EUR, USD).")
    payment_method: PaymentMethod = Field(
        description="Payment method: direct, reimbursement, or unknown."
    )

    @classmethod
    def default(cls) -> "CostEstimateImportDto":
        return cls(amount=Decimal("0.00"), currency="EUR", payment_method=PaymentMethod.Unknown)


class SeparateContactImportDto(BaseModel):
    """Contact for communication about this request if it is not handled by the publication authors."""

    name: str = Field(description="Name of the separate contact.")
    email: str = Field(description="Email address of the separate contact.")

    @classmethod
    def default(cls) -> "SeparateContactImportDto":
        return cls(name="", email="")


class FundingRequestImportDto(BaseModel):
    """A single funding request to import."""

    request_date: datetime.date = Field(description="Date of the request (YYYY-MM-DD).")
    legacy_request_id: str = Field(
        default="",
        description="Identifier from the legacy system; also used as the error key in import reports "
        "and to link invoice positions.",
    )
    review: ReviewImportDto = Field(
        default_factory=ReviewImportDto, description="Review decision for this request."
    )
    publication: PublicationImportDto = Field(description="Publication metadata.")
    research_funding: list[ResearchFundingImportDto] = Field(
        default_factory=list, description="Third-party funding sources for this publication."
    )
    estimated_cost: CostEstimateImportDto = Field(
        default_factory=CostEstimateImportDto.default,
        description="Estimated publication costs.",
    )
    request_remarks: str = Field(default="", description="Notes or comments about the request.")
    separate_contact: SeparateContactImportDto = Field(
        default_factory=SeparateContactImportDto.default,
        description="Separate contact when communication is not handled by the authors. "
        "Also accepts the legacy misspelled key 'seperate_contact'.",
        validation_alias=AliasChoices("separate_contact", "seperate_contact"),
        serialization_alias="separate_contact",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Label names; labels are created with default colors if they do not exist.",
    )
    request_id: str | None = Field(
        default=None,
        description="CODA public request ID (coda-YYYYMMDD-XXXXXXXXXXXX); optional, currently not "
        "used by the import service.",
    )


class FundingRequestImportListDto(BaseModel):
    """Root object of the funding request import file."""

    requests: list[FundingRequestImportDto] = Field(description="Funding requests to import.")
