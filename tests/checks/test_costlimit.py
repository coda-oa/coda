from coda.checks.checklist import CheckResult
from coda.checks.costlimit import CostLimitCheck


class ApplicationTestDouble:
    def __init__(self, cost: int, currency: str = "EUR") -> None:
        self.cost = cost
        self.currency = currency


def one2one(amount: int, origin: str, target: str) -> int:
    return amount


def make_sut(cost: int, currency: str = "EUR") -> CostLimitCheck:
    return CostLimitCheck(cost, currency=currency, converter=one2one)


def test__cost_limit_check__when_application_cost_is_below_threshold__returns_success() -> None:
    app = ApplicationTestDouble(999)
    sut = make_sut(1000)

    result = sut(app)

    assert result == CheckResult.SUCCESS


def test__cost_limit_check__when_application_cost_is_above_threshold__returns_failure() -> None:
    app = ApplicationTestDouble(1001)
    sut = make_sut(1000)

    result = sut(app)

    assert result == CheckResult.FAILURE


def test__cost_above_limit_in_different_currency__returns_failure() -> None:
    def usd2eur(amount: int, origin: str, target: str) -> int:
        return amount * 2

    app = ApplicationTestDouble(1000, "USD")
    sut = CostLimitCheck(1000, currency="EUR", converter=usd2eur)

    result = sut(app)

    assert result == CheckResult.FAILURE


def test__cost_below_limit_in_different_currency__returns_success() -> None:
    def usd2eur(amount: int, origin: str, target: str) -> int:
        return amount // 2

    app = ApplicationTestDouble(1000, "USD")
    sut = CostLimitCheck(1000, currency="EUR", converter=usd2eur)

    result = sut(app)

    assert result == CheckResult.SUCCESS
