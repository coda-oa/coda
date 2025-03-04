from coda.checks.checklist import CheckFailed, CheckResult, CheckSuccessful
from coda.fundingrequest import AnyFundingRequest
from coda.money import CurrencyExchange, Money


class CostLimitCheck:
    name = "Cost limit check"

    def __init__(self, limit: Money, converter: CurrencyExchange) -> None:
        self.limit = limit
        self.converter = converter

    @property
    def description(self) -> str:
        return f"Cost must not exceed {self.limit}"

    def __call__(self, fundingrequest: AnyFundingRequest) -> CheckResult:
        converted_cost = fundingrequest.estimated_cost.amount.convert_to(
            self.limit.currency, self.converter
        )

        if converted_cost <= self.limit:
            return CheckSuccessful()
        else:
            return CheckFailed(f"Cost exceeds limit of {self.limit}")
