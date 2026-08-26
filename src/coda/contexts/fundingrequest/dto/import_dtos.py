"""Import DTOs for fundingrequest import workflow.

This module consolidates all Pydantic DTOs used for JSON import validation.
DTOs are organized by entity type for clarity.
"""

import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

import pydantic

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


LinkType = Annotated[str, pydantic.PlainValidator(_valid_link_type)]
MaybeIssn = Annotated[str, pydantic.PlainValidator(_maybe_issn)]
Orcid = Annotated[str, pydantic.PlainValidator(orcid.Orcid)]


# === Author DTOs ===


class AuthorImportDto(pydantic.BaseModel):
    name: str
    email: str
    orcid: Orcid | None = None
    affiliation: str | None = None
    role: Role = Role.CO_AUTHOR


# === Contract DTOs ===


class ContractImportDto(pydantic.BaseModel):
    name: str
    year: pydantic.PositiveInt


# === Vocabulary DTOs ===


class ConceptImportDto(pydantic.BaseModel):
    name: str = ""
    vocabulary_name: str = ""
    concept_id: str = ""


# === Review DTOs ===


class DecidedFundingImportDto(pydantic.BaseModel):
    amount: Decimal
    currency: str

    @classmethod
    def default(cls) -> "DecidedFundingImportDto":
        return cls(amount=Decimal("0.00"), currency="EUR")


class ReviewImportDto(pydantic.BaseModel):
    result: ReviewResult = pydantic.Field(default=ReviewResult.Open)
    funding: DecidedFundingImportDto = DecidedFundingImportDto.default()
    remarks: str = ""


# === Publication DTOs ===


PublishingStateOptions = Literal["unknown", "submitted", "accepted", "rejected", "published"]


class LinkImportDto(pydantic.BaseModel):
    type: LinkType
    value: str


class PublishingStateImportDto(pydantic.BaseModel):
    state: PublishingStateOptions = "unknown"
    online_date: datetime.date | None = None
    print_date: datetime.date | None = None


class PublicationImportDto(pydantic.BaseModel):
    title: str
    kind: Literal["article", "monograph"]
    eissn: MaybeIssn = pydantic.Field(default="")
    journal_name: str = "Imported nameless journal"
    publisher_name: str = "Imported nameless publisher"
    authors: list[AuthorImportDto] = pydantic.Field(default_factory=list)
    license: License = License.Unknown
    publishing_state: PublishingStateImportDto = pydantic.Field(
        default_factory=PublishingStateImportDto
    )
    open_access_type: OpenAccessType
    links: list[LinkImportDto] = pydantic.Field(default_factory=list)
    contracts: list[ContractImportDto] = pydantic.Field(default_factory=list)
    subject_area: ConceptImportDto = pydantic.Field(default_factory=ConceptImportDto)
    publication_type: ConceptImportDto = pydantic.Field(default_factory=ConceptImportDto)

    @pydantic.model_validator(mode="after")
    def verify_eissn(self) -> Self:
        if self.kind == "article" and self.eissn == "":
            raise pydantic.ValidationError("EISSN must be provided for articles")

        return self


# === FundingRequest DTOs ===


class ResearchFundingImportDto(pydantic.BaseModel):
    funder: str
    project_id: str
    project_name: str = ""


class CostEstimateImportDto(pydantic.BaseModel):
    amount: Decimal
    currency: str
    payment_method: PaymentMethod

    @classmethod
    def default(cls) -> "CostEstimateImportDto":
        return cls(amount=Decimal("0.00"), currency="EUR", payment_method=PaymentMethod.Unknown)


class SeperateContactImportDto(pydantic.BaseModel):
    """Note: 'Seperate' typo kept for backward compatibility."""

    name: str
    email: str

    @classmethod
    def default(cls) -> "SeperateContactImportDto":
        return cls(name="", email="")


class FundingRequestImportDto(pydantic.BaseModel):
    request_date: datetime.date
    legacy_request_id: str = ""
    review: ReviewImportDto = pydantic.Field(default_factory=ReviewImportDto)
    publication: PublicationImportDto
    research_funding: list[ResearchFundingImportDto] = pydantic.Field(default_factory=list)
    estimated_cost: CostEstimateImportDto = pydantic.Field(
        default_factory=CostEstimateImportDto.default
    )
    request_remarks: str = ""
    seperate_contact: SeperateContactImportDto = pydantic.Field(
        default_factory=SeperateContactImportDto.default
    )
    labels: list[str] = pydantic.Field(default_factory=list)
    request_id: str | None = None


class FundingRequestImportListDto(pydantic.BaseModel):
    requests: list[FundingRequestImportDto]
