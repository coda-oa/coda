from decimal import Decimal

import pydantic

from coda.domain.fundingrequest import FundingRequestId, Review, ReviewResult
from coda.domain.money import Currency, Money


class DecidedFundingImportDto(pydantic.BaseModel):
    amount: Decimal
    currency: str

    @classmethod
    def default(cls) -> "DecidedFundingImportDto":
        return cls(amount=Decimal("0.00"), currency="EUR")

    def parse(self) -> Money:
        return Money(self.amount, Currency.from_code(self.currency))


class ReviewImportDto(pydantic.BaseModel):
    result: ReviewResult = pydantic.Field(default=ReviewResult.Open)
    funding: DecidedFundingImportDto = DecidedFundingImportDto.default()
    remarks: str = ""

    def parse(self, fundingrequest: FundingRequestId) -> Review:
        return Review(
            fundingrequest=fundingrequest,
            result=self.result,
            decided_funding=self.funding.parse(),
            remarks=self.remarks,
        )
