"""Capacity rule for budgets.

A new commitment is allowed iff committed + new <= amount + allowance, where
an empty allowance means unbounded when going over is allowed. Functions
return a verdict; surfacing a rejection (message, exception) is the service
layer's decision."""

from dataclasses import dataclass

from coda.domain.money import Money


@dataclass(frozen=True)
class BudgetBookings:
    amount: Money
    reserved: Money
    spent: Money
    credited: Money
    debit: Money
    allow_over: bool = False
    allowance: Money | None = None


@dataclass(frozen=True)
class CapacityVerdict:
    allowed: bool
    available_after: Money  # negative = how far the commitment goes past the limit


def committed(bookings: BudgetBookings) -> Money:
    return bookings.reserved + bookings.spent - bookings.credited + bookings.debit


def available(bookings: BudgetBookings) -> Money:
    return bookings.amount - committed(bookings)


def check_capacity(bookings: BudgetBookings, new: Money) -> CapacityVerdict:
    limit: Money | None
    if not bookings.allow_over:
        limit = bookings.amount
    elif bookings.allowance is None:
        limit = None  # unbounded
    else:
        limit = bookings.amount + bookings.allowance

    if limit is not None and committed(bookings) + new > limit:
        return CapacityVerdict(allowed=False, available_after=available(bookings) - new)

    return CapacityVerdict(allowed=True, available_after=available(bookings) - new)


def check_transfer_out(bookings: BudgetBookings, amount: Money) -> CapacityVerdict:
    """Checks whether an outgoing transfer fits the source budget.

    An outgoing positive transfer counts as a commitment on the source. A
    debt transfer (negative amount) is exempt and leaves the source's
    available unchanged."""
    if amount.amount < 0:
        return CapacityVerdict(allowed=True, available_after=available(bookings))

    return check_capacity(bookings, amount)
