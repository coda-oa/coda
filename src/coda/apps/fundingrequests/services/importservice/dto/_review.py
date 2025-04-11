from decimal import Decimal

import pydantic

from coda.domain.fundingrequest import ReviewResult


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
