"""Budget accounting services (docs/design/budget-system.md §4, §6).

The capacity rule itself lives in the domain
(`coda.domain.finance.budget_capacity`); this module assembles a budget's
bookings from persisted rows and decides how rejections surface. Enforcement
applies to review decisions and manual/UI funding assignments — invoice
import is a recorded fact and does not run these checks."""

from coda.apps.invoices import budget_query
from coda.apps.invoices.funding_source_repository import get_by_id
from coda.apps.invoices.models import (
    BudgetLedgerEntry as BudgetLedgerEntryModel,
)
from coda.apps.invoices.models import (
    BudgetTransfer as BudgetTransferModel,
)
from coda.apps.invoices.models import (
    FundingAssignment as FundingAssignmentModel,
)
from coda.domain.errors import DomainError
from coda.domain.finance.budget_capacity import (
    BudgetBookings,
    CapacityVerdict,
    check_capacity,
    check_transfer_out,
)
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import FundingSourceId, Invoice, InvoiceId
from coda.domain.money import Currency, Money


class BudgetCapacityExceededError(DomainError):
    pass


def capacity_verdict(funding_source_id: FundingSourceId, new: Money) -> CapacityVerdict:
    budget = _budget(funding_source_id)
    return check_capacity(_bookings(funding_source_id, budget), new)


def ensure_capacity(funding_source_id: FundingSourceId, new: Money) -> None:
    budget = _budget(funding_source_id)
    if new.currency.code != budget.amount.currency.code:
        return  # rate-pending commitment: invisible to the check (spec §4)

    verdict = capacity_verdict(funding_source_id, new)
    if not verdict.allowed:
        over = verdict.available_after * -1
        raise BudgetCapacityExceededError(
            f"committing {new.amount} {new.currency.code} to budget '{budget.name}' "
            f"exceeds its capacity by {over.amount} {over.currency.code}"
        )


def ensure_assignment_capacity(invoice: Invoice) -> None:
    """Capacity rule at the invoice-assignment commitment point (spec §4).

    Only budget-type funding sources are checked; institution sources are
    cost-sharing and carry no budget. Foreign-currency assignments are
    rate-pending and invisible to the check (enforced in ensure_capacity)."""
    for position in invoice.positions:
        for assignment in position.funding_assignments():
            source = assignment.funding_source
            if not isinstance(source, Budget) or source.id is None:
                continue

            ensure_capacity(source.id, assignment.amount)


def transfer_out_verdict(funding_source_id: FundingSourceId, amount: Money) -> CapacityVerdict:
    """The capacity rule applied to an outgoing transfer (spec §5): positive
    transfers are commitments on the source; debt transfers are exempt."""
    budget = _budget(funding_source_id)
    bookings = _bookings(funding_source_id, budget)
    return check_transfer_out(bookings, amount)


def create_transfer(
    source_id: FundingSourceId, target_id: FundingSourceId, amount: Money, provenance_note: str
) -> None:
    if source_id == target_id:
        raise InvalidTransfer("a budget cannot transfer to itself")

    source = _transfer_endpoint(source_id)
    _transfer_endpoint(target_id)
    if amount.currency.code != source.amount.currency.code:
        raise InvalidTransfer(
            "transfers are booked in the budget's currency "
            f"({source.amount.currency.code}), not {amount.currency.code}"
        )

    verdict = transfer_out_verdict(source_id, amount)
    if not verdict.allowed:
        over = verdict.available_after * -1
        raise BudgetCapacityExceededError(
            f"transferring {amount.amount} {amount.currency.code} from budget "
            f"'{source.name}' exceeds its capacity by {over.amount} {over.currency.code}"
        )

    transfer = BudgetTransferModel.objects.create(
        source_id=source_id,
        target_id=target_id,
        amount=amount.amount,
        provenance_note=provenance_note,
    )
    record_transfer(source_id, amount, transfer.pk)
    record_transfer(target_id, amount, transfer.pk)


class InvalidTransfer(DomainError):
    pass


def record_commitment(
    budget_id: FundingSourceId,
    amount: Money,
    *,
    review_split: int | None = None,
    funding_assignment: int | None = None,
) -> None:
    _append_ledger_entry(
        budget_id,
        BudgetLedgerEntryModel.Event.COMMITMENT,
        amount,
        review_split=review_split,
        funding_assignment=funding_assignment,
    )


def record_assignment_commitments(invoice_id: InvoiceId) -> None:
    for row in FundingAssignmentModel.objects.filter(position__invoice_id=invoice_id):
        if row.funding_source is None or row.funding_source.type != "budget":
            continue
        assert row.funding_source_id is not None
        _append_ledger_entry(
            FundingSourceId(row.funding_source_id),
            BudgetLedgerEntryModel.Event.COMMITMENT,
            Money(row.amount, Currency[row.position.cost_currency]),
            funding_assignment=row.pk,
        )


def record_payments(invoice_id: InvoiceId) -> None:
    for row in FundingAssignmentModel.objects.filter(position__invoice_id=invoice_id):
        if row.funding_source is None or row.funding_source.type != "budget":
            continue
        assert row.funding_source_id is not None
        _append_ledger_entry(
            FundingSourceId(row.funding_source_id),
            BudgetLedgerEntryModel.Event.PAYMENT,
            Money(row.amount, Currency[row.position.cost_currency]),
            funding_assignment=row.pk,
        )


def record_transfer(budget_id: FundingSourceId, amount: Money, transfer_id: int) -> None:
    _append_ledger_entry(
        budget_id, BudgetLedgerEntryModel.Event.TRANSFER, amount, transfer=transfer_id
    )


def _append_ledger_entry(
    budget_id: FundingSourceId,
    event: str,
    amount: Money,
    *,
    review_split: int | None = None,
    funding_assignment: int | None = None,
    transfer: int | None = None,
) -> None:
    BudgetLedgerEntryModel.objects.create(
        budget_id=budget_id,
        event=event,
        amount=amount.amount,
        currency=amount.currency.code,
        review_split_id=review_split,
        funding_assignment_id=funding_assignment,
        transfer_id=transfer,
    )


def _transfer_endpoint(funding_source_id: FundingSourceId) -> Budget:
    source = get_by_id(funding_source_id)
    if not isinstance(source, Budget):
        raise InvalidTransfer(f"funding source {funding_source_id} is not a budget")
    return source


def _bookings(funding_source_id: FundingSourceId, budget: Budget) -> BudgetBookings:
    balance = budget_query.budget_balances(funding_source_id)
    return BudgetBookings(
        amount=budget.amount,
        reserved=balance.reserved,
        spent=balance.spent,
        credited=balance.credited,
        debit=balance.debit,
        allow_over=budget.allow_over,
        allowance=budget.allowance,
    )


def _budget(funding_source_id: FundingSourceId) -> Budget:
    source = get_by_id(funding_source_id)
    assert isinstance(source, Budget)
    return source
