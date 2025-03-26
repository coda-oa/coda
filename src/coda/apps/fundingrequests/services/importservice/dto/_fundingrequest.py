import datetime
from decimal import Decimal

import pydantic

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingOrganization
from coda.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    NoContact,
    Payment,
    PaymentMethod,
)
from coda.fundingrequest.identity import PublicFundingRequestId
from coda.money import Currency, Money
from coda.string import NonEmptyStr

from ._publication import PublicationImportDto
from ._review import ReviewImportDto


class ResearchFundingImportDto(pydantic.BaseModel):
    funder: str
    project_id: str
    project_name: str = ""

    def parse(self) -> ExternalFunding:
        org = repository.get_funding_organization_by_name(self.funder)
        if org is None:
            org = FundingOrganization.objects.create(name=self.funder)

        return ExternalFunding(
            organization=FundingOrganizationId(org.id),
            project_id=NonEmptyStr(self.project_id),
            project_name=self.project_name,
        )


class CostEstimateImportDto(pydantic.BaseModel):
    amount: Decimal
    currency: str
    payment_method: PaymentMethod

    @classmethod
    def default(cls) -> "CostEstimateImportDto":
        return cls(amount=Decimal("0.00"), currency="EUR", payment_method=PaymentMethod.Unknown)

    def parse(self) -> Payment:
        return Payment(
            amount=Money(self.amount, currency=Currency.from_code(self.currency)),
            method=self.payment_method,
        )


class SeperateContactImportDto(pydantic.BaseModel):
    name: str
    email: str

    @classmethod
    def default(cls) -> "SeperateContactImportDto":
        return cls(name="", email="")

    def parse(self) -> FundingRequestContact:
        if self.name and self.email:
            return FilledContact(name=NonEmptyStr(self.name), email=self.email)

        return NoContact


class FundingRequestImportDto(pydantic.BaseModel):
    request_date: datetime.date
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

    def parse(self) -> AnyFundingRequest:
        fundingrequest = FundingRequest.new(
            publication=self.publication.parse(),
            estimated_cost=self.estimated_cost.parse(),
            request_id=PublicFundingRequestId.create(self.request_date),
            request_remarks=self.request_remarks,
            external_funding=[funding.parse() for funding in self.research_funding],
            extra_contact=self.seperate_contact.parse(),
        )

        return fundingrequest


class FundingRequestImportListDto(pydantic.BaseModel):
    requests: list[FundingRequestImportDto]
