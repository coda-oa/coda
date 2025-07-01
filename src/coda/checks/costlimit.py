from decimal import Decimal
from typing import Any
from coda.checks.checklist import CheckFailed, CheckResult, CheckSuccessful
from coda.domain.fundingrequest import FundingRequest, TPublication
from coda.domain.money import Currency, CurrencyExchange, Money


class CostLimitCheck:
    name = "Cost limit check"

    def __init__(
        self, converter: CurrencyExchange, *, limit: Money = Money(0, Currency.EUR)
    ) -> None:
        self.limit = limit
        self.converter = converter
        self._params = {"limit": limit.amount, "currency": limit.currency.code}

    @property
    def params(self) -> dict[str, Any]:
        return self._params

    @params.setter
    def params(self, value: dict[str, Any]) -> None:
        self._params = value
        self.limit = Money(Decimal(value["limit"]), Currency.from_code(value["currency"]))

    @property
    def description(self) -> str:
        return f"Cost must not exceed {self.limit}"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        converted_cost = fundingrequest.estimated_cost.amount.convert_to(
            self.limit.currency, self.converter
        )

        if converted_cost <= self.limit:
            return CheckSuccessful()
        else:
            return CheckFailed(f"Cost exceeds limit of {self.limit}")
