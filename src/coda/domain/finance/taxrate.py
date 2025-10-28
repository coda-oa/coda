from decimal import Decimal
from typing import Self

from coda.domain import errors


class TaxRate(Decimal):
    __slots__ = ()

    def __new__(cls, value: Decimal | float | str) -> Self:
        v = Decimal(value)
        if v < 0:
            raise errors.DomainError("Tax rate must be positive")

        return super().__new__(cls, v.quantize(Decimal("0.0000")))

    @classmethod
    def from_percentage(cls, value: Decimal | float | str) -> "TaxRate":
        return TaxRate(cls(value) / 100)

    def percentage(self) -> Decimal:
        return self * 100
