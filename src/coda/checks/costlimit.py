from dataclasses import dataclass
from typing import Callable, Protocol

from coda.checks.checklist import CheckResult


class Application(Protocol):
    @property
    def cost(self) -> int:
        ...

    @property
    def currency(self) -> str:
        ...


@dataclass
class Money:
    amount: int
    currency: str

    def convert_to(
        self, target_currency: str, converter: Callable[[int, str, str], int]
    ) -> "Money":
        if self.currency == target_currency:
            return self

        return Money(
            converter(self.amount, self.currency, target_currency),
            target_currency,
        )


class CostLimitCheck:
    def __init__(
        self,
        limit: int,
        *,
        currency: str = "EUR",
        converter: Callable[[int, str, str], int],
    ) -> None:
        self.limit = Money(limit, currency)
        self.currency = currency
        self.converter = converter

    def __call__(self, app: Application) -> CheckResult:
        money = Money(app.cost, app.currency)
        converted_cost = money.convert_to(self.currency, self.converter)

        if converted_cost.amount <= self.limit.amount:
            return CheckResult.SUCCESS
        else:
            return CheckResult.FAILURE
