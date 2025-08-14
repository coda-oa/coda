import datetime
from decimal import Decimal

import pydantic

from coda.domain.fundingrequest import PaymentMethod

from ._publication import PublicationImportDto
from ._review import ReviewImportDto


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


class FundingRequestImportListDto(pydantic.BaseModel):
    requests: list[FundingRequestImportDto]
