from decimal import Decimal

from coda.checks.checklist import CheckFailed, CheckSuccessful
from coda.checks.costlimit import CostLimitCheck
from coda.money import Currency, Money
from tests import domainfactory

LIMIT = Money(Decimal(1000), currency=Currency.EUR)
UNDER_LIMIT = Money(LIMIT.amount - 1, currency=Currency.EUR)
OVER_LIMIT = Money(LIMIT.amount + 1, currency=Currency.EUR)


class ApplicationTestDouble:
    def __init__(self, cost: Money) -> None:
        self.cost = cost


def one2one(origin: Currency, target: Currency) -> Decimal:
    return Decimal(1)


def make_sut(cost: Money = LIMIT) -> CostLimitCheck:
    return CostLimitCheck(cost, converter=one2one)


def test__cost_limit_check__when_application_cost_is_below_threshold__returns_success() -> None:
    app = domainfactory.fundingrequest()
    app.estimated_cost.amount = UNDER_LIMIT
    sut = make_sut(LIMIT)

    result = sut(app)

    assert result == CheckSuccessful()


def test__cost_limit_check__when_application_cost_is_above_threshold__returns_failure() -> None:
    app = domainfactory.fundingrequest()
    app.estimated_cost.amount = OVER_LIMIT
    sut = make_sut(LIMIT)

    result = sut(app)

    assert result == CheckFailed(f"Cost exceeds limit of {LIMIT}")


def test__cost_above_limit_in_different_currency__returns_failure() -> None:
    def over_limit_exchange(origin: Currency, target: Currency) -> Decimal:
        return Decimal(2)

    app = domainfactory.fundingrequest()
    app.estimated_cost.amount = Money(LIMIT.amount, Currency.USD)
    sut = CostLimitCheck(LIMIT, converter=over_limit_exchange)

    result = sut(app)

    assert result == CheckFailed(f"Cost exceeds limit of {LIMIT}")


def test__cost_below_limit_in_different_currency__returns_success() -> None:
    def under_limit_exchange(origin: Currency, target: Currency) -> Decimal:
        return Decimal("0.5")

    app = domainfactory.fundingrequest()
    app.estimated_cost.amount = Money(LIMIT.amount, Currency.USD)
    sut = CostLimitCheck(LIMIT, converter=under_limit_exchange)

    result = sut(app)

    assert result == CheckSuccessful()
