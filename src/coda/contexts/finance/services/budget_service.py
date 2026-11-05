"""Budget accounting services (docs/design/budget-system.md §4, §6).

The capacity rule itself lives in the domain
(`coda.domain.finance.budget_capacity`); this module assembles a budget's
bookings from persisted rows and decides how rejections surface. Enforcement
applies to review decisions and manual/UI funding assignments — invoice
import is a recorded fact and does not run these checks."""

from collections import Counter
from collections.abc import Iterable
from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Round

from coda.apps.invoices import budget_query
from coda.apps.invoices.funding_source_repository import get_by_id
from coda.apps.invoices.models import BudgetLedgerEntry as BudgetLedgerEntryModel
from coda.apps.invoices.models import BudgetTransfer as BudgetTransferModel
from coda.apps.invoices.models import FundingAssignment as FundingAssignmentModel
from coda.domain.errors import DomainError
from coda.domain.finance.budget_capacity import (
    BudgetBookings,
    CapacityVerdict,
    check_capacity,
    check_transfer_out,
)
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import FundingSourceId, Invoice, InvoiceId
from coda.domain.finance.taxable_money import CostBasis
from coda.domain.money import Currency, Money


class BudgetCapacityExceededError(DomainError):
    pass


def committed_per_funding_source(
    commitments: Iterable[tuple[FundingSourceId, Money]],
) -> dict[FundingSourceId, Money]:
    """Sums commitments per funding source — a source's capacity must be
    checked against the total committed to it, not against each commitment."""
    totals: dict[FundingSourceId, Money] = {}
    for funding_source, amount in commitments:
        totals[funding_source] = totals.get(funding_source, Money(0, amount.currency)) + amount
    return totals


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
    rate-pending and invisible to the check (enforced in ensure_capacity).

    Only the *change* over the invoice's own persisted assignments is a new
    commitment: existing commitments are never re-checked (spec §4), so
    re-saving an invoice never counts its existing commitment against itself —
    even if other invoices consumed the budget in the meantime. Both sides of
    the delta are gross-of-tax: the new amounts read via
    ``funding_assignments(CostBasis.gross)``, the persisted totals via the
    same gross expression the read model uses."""
    previous = _persisted_assignment_totals(invoice.id)
    for position in invoice.positions:
        for assignment in position.funding_assignments(CostBasis.gross):
            source = assignment.funding_source
            if not isinstance(source, Budget) or source.id is None:
                continue

            key = (source.id, assignment.amount.currency.code)
            already_committed = Money(previous.get(key, Decimal(0)), assignment.amount.currency)
            delta = assignment.amount - already_committed
            if delta.amount > 0:
                ensure_capacity(source.id, delta)


def _persisted_assignment_totals(
    invoice_id: InvoiceId | None,
) -> dict[tuple[int, str], Decimal]:
    """Per (budget, cost currency) gross-of-tax totals of a saved invoice's
    assignments — the same rounded gross expression the read model uses, so
    the delta never compares a net snapshot against a gross commitment."""
    if invoice_id is None:
        return {}

    totals: dict[tuple[int, str], Decimal] = {}
    cost_currencies = (
        FundingAssignmentModel.objects.filter(position__invoice_id=invoice_id)
        .values_list("position__cost_currency", flat=True)
        .order_by()
        .distinct()
    )
    for code in cost_currencies:
        precision = Currency[code].minor_units
        gross = Round(
            F("amount") * (1 + F("position__tax_rate")),
            precision=precision,
            output_field=DecimalField(max_digits=24, decimal_places=precision),
        )
        rows = (
            FundingAssignmentModel.objects.filter(
                position__invoice_id=invoice_id, position__cost_currency=code
            )
            .order_by()
            .values("funding_source_id")
            .annotate(
                total=Sum(gross, output_field=DecimalField(max_digits=24, decimal_places=precision))
            )
        )
        for row in rows:
            totals[(row["funding_source_id"], code)] = row["total"] or Decimal(0)
    return totals


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


def _booked_amount(row: FundingAssignmentModel) -> Money:
    """The assignment's gross-of-tax amount in the original currency:
    net amount × (1 + the position's tax rate); ``Money`` rounds to the
    currency's minor units. VAT rows self-handle (stored rate 0)."""
    gross = row.amount * (1 + row.position.tax_rate)
    return Money(gross, Currency[row.position.cost_currency])


def record_assignment_commitments(
    invoice_id: InvoiceId, previous: Counter[tuple[int, str, Decimal]] | None = None
) -> None:
    """Book one commitment ledger row per assignment (spec §4).

    ``previous`` carries the invoice's budget assignments as persisted before
    the save (multiset of funding-source id, cost currency, amount).
    (source, currency, amount) triples already present in ``previous`` are
    skipped, so re-saving an invoice does not book duplicate commitment rows;
    only genuinely new or changed assignments book an event."""
    previous = previous or Counter()
    for row in FundingAssignmentModel.objects.filter(position__invoice_id=invoice_id):
        if row.funding_source is None or row.funding_source.type != "budget":
            continue
        assert row.funding_source_id is not None
        key = (row.funding_source_id, row.position.cost_currency, row.amount)
        if previous[key] > 0:
            previous[key] -= 1
            continue
        _append_ledger_entry(
            FundingSourceId(row.funding_source_id),
            BudgetLedgerEntryModel.Event.COMMITMENT,
            _booked_amount(row),
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
            _booked_amount(row),
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
