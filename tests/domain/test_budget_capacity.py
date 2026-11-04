from coda.domain.finance.budget_capacity import (
    BudgetBookings,
    check_capacity,
    check_transfer_out,
)
from coda.domain.money import Currency, Money

EUR = Currency.EUR


def bookings(
    amount: Money | None = None,
    reserved: Money | None = None,
    spent: Money | None = None,
    credited: Money | None = None,
    debit: Money | None = None,
    allow_over: bool = False,
    allowance: Money | None = None,
) -> BudgetBookings:
    return BudgetBookings(
        amount=amount or Money(100, EUR),
        reserved=reserved or Money(0, EUR),
        spent=spent or Money(0, EUR),
        credited=credited or Money(0, EUR),
        debit=debit or Money(0, EUR),
        allow_over=allow_over,
        allowance=allowance,
    )


def test__budget_with_room_left__commit_within_amount__is_allowed_with_remaining_available() -> (
    None
):
    state = bookings(reserved=Money(20, EUR), spent=Money(40, EUR))

    verdict = check_capacity(state, Money(40, EUR))

    assert verdict.allowed is True
    assert verdict.available_after == Money(0, EUR)


def test__budget_exhausted__commit_beyond_amount__is_rejected() -> None:
    state = bookings(reserved=Money(60, EUR), spent=Money(40, EUR))

    verdict = check_capacity(state, Money(1, EUR))

    assert verdict.allowed is False
    assert verdict.available_after == Money(-1, EUR)  # amount − committed − new


def test__budget_allowing_over_without_allowance__commit_beyond_amount__is_allowed() -> None:
    state = bookings(reserved=Money(60, EUR), spent=Money(40, EUR), allow_over=True)

    verdict = check_capacity(state, Money(500, EUR))

    assert verdict.allowed is True
    assert verdict.available_after == Money(-500, EUR)


def test__budget_allowing_over_with_allowance__commit_up_to_allowance__is_allowed() -> None:
    state = bookings(
        reserved=Money(100, EUR),
        spent=Money(40, EUR),
        allow_over=True,
        allowance=Money(50, EUR),
    )

    verdict = check_capacity(state, Money(10, EUR))  # committed 140 + 10 = 150 = amount + allowance

    assert verdict.allowed is True
    assert verdict.available_after == Money(-50, EUR)  # amount − committed − new


def test__budget_allowing_over_with_allowance__commit_beyond_allowance__is_rejected() -> None:
    state = bookings(
        reserved=Money(100, EUR),
        spent=Money(40, EUR),
        allow_over=True,
        allowance=Money(50, EUR),
    )

    verdict = check_capacity(state, Money(11, EUR))

    assert verdict.allowed is False
    assert verdict.available_after == Money(-51, EUR)  # amount − committed − new


def test__transfer_out_from_budget_with_room__within_amount__is_allowed() -> None:
    state = bookings(reserved=Money(20, EUR), spent=Money(40, EUR))

    verdict = check_transfer_out(state, Money(40, EUR))

    assert verdict.allowed is True
    assert verdict.available_after == Money(0, EUR)


def test__transfer_out_beyond_capacity__is_rejected() -> None:
    state = bookings(reserved=Money(60, EUR), spent=Money(40, EUR))

    verdict = check_transfer_out(state, Money(1, EUR))

    assert verdict.allowed is False
    assert verdict.available_after == Money(-1, EUR)


def test__debt_transfer_out_from_exhausted_budget__is_exempt_and_keeps_available() -> None:
    state = bookings(reserved=Money(60, EUR), spent=Money(40, EUR))

    verdict = check_transfer_out(state, Money(-500, EUR))

    assert verdict.allowed is True
    assert verdict.available_after == Money(0, EUR)  # debt transfer does not change the source
