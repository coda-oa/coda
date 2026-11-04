from dataclasses import dataclass, field
from typing import Literal

from coda.domain.author import InstitutionId
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.money import Currency, Money


@dataclass
class Budget:
    id: FundingSourceId | None
    name: str = field(compare=False)
    amount: Money = field(default_factory=lambda: Money(0, Currency.EUR), compare=False)
    period: DateRange = field(default_factory=DateRange.create, compare=False)
    allow_over: bool = field(default=False, compare=False)
    allowance: Money | None = field(default=None, compare=False)

    @classmethod
    def new(
        cls,
        name: str,
        *,
        amount: Money | None = None,
        period: DateRange | None = None,
        allow_over: bool = False,
        allowance: Money | None = None,
    ) -> "Budget":
        return cls(
            None,
            name,
            amount=amount or Money(0, Currency.EUR),
            period=period or DateRange.create(),
            allow_over=allow_over,
            allowance=allowance,
        )

    def identity(self) -> FundingSourceId | None:
        return self.id

    def kind(self) -> Literal["budget"]:
        return "budget"


@dataclass
class SplitSource:
    id: FundingSourceId | None = field(compare=False)
    institution: InstitutionId
    institution_name: str = field(compare=False)

    @classmethod
    def new(cls, institution: InstitutionId, institution_name: str) -> "SplitSource":
        return cls(None, institution, institution_name)

    @property
    def name(self) -> str:
        return self.institution_name

    def identity(self) -> InstitutionId:
        return self.institution

    def kind(self) -> Literal["institution"]:
        return "institution"


type FundingSource = Budget | SplitSource
