from typing import Protocol

from coda.checks.checklist import CheckResult
from coda.money import CurrencyExchange, Money


class Application(Protocol):
    @property
    def cost(self) -> Money:
        ...


class CostLimitCheck:
    def __init__(self, limit: Money, converter: CurrencyExchange) -> None:
        self.limit = limit
        self.converter = converter

    def __call__(self, app: Application) -> CheckResult:
        converted_cost = app.cost.convert_to(self.limit.currency, self.converter)

        if converted_cost <= self.limit:
            return CheckResult.SUCCESS
        else:
            return CheckResult.FAILURE
