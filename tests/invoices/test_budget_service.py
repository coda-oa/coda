from decimal import Decimal

import pytest

from coda.apps.invoices import budget_query, funding_source_repository
from coda.apps.invoices import repository as invoice_repository
from coda.apps.invoices.models import BudgetLedgerEntry, BudgetTransfer
from coda.contexts.finance.services import budget_service, invoice_service
from coda.domain.author import InstitutionId
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import CreditorId
from coda.domain.finance.invoice_positions import FreeItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from tests import domainfactory, modelfactory
from tests.invoices import budget_setup

EUR = Currency.EUR
USD = Currency.USD


@pytest.mark.django_db
def test__budget_with_room_left__ensure_capacity__does_not_raise() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)

    # The guard returns the verdict it enforced on — allowed, with the
    # remaining headroom (10000 amount − 2500 spent − 5000 new).
    verdict = budget_service.ensure_capacity(budget_id, Money("5000", EUR))
    assert verdict is not None
    assert verdict.allowed is True
    assert verdict.available_after == Money("2500", EUR)


@pytest.mark.django_db
def test__foreign_currency_commitment__is_invisible_to_the_capacity_check() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    budget_setup.an_invoice_with_assignment(Money("1000", EUR), budget, paid=True)

    # A rate-pending commitment is invisible to the check: the guard reports
    # it as unchecked (None) instead of a verdict.
    assert budget_service.ensure_capacity(budget_id, Money("5000", USD)) is None

    # The contrast pins the rule: the budget's EUR capacity is fully consumed
    # by the EUR booking — a fresh EUR commitment is rejected — while the
    # rate-pending USD commitment of 5× the budget passed the check above.
    with pytest.raises(budget_service.BudgetCapacityExceededError):
        budget_service.ensure_capacity(budget_id, Money("1", EUR))


@pytest.mark.django_db
def test__re_saving_invoice_with_assignment__does_not_double_count_its_own_commitment() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    invoice = budget_setup.an_unsaved_invoice_with_assignment(Money("600", EUR), budget)

    invoice_service.save(invoice)
    balance_after_first_save = budget_query.budget_balances(budget_id)
    # Re-saving an existing invoice (edit) must not count its own persisted
    # assignment again — otherwise any edit of a fully-committed budget fails.
    invoice_service.save(invoice)

    # The re-save is a no-op for the budget: same reserved, same available.
    assert budget_query.budget_balances(budget_id) == balance_after_first_save
    assert budget_query.budget_balances(budget_id).reserved == Money("600", EUR)


@pytest.mark.django_db
def test__re_saving_invoice__after_other_invoices_consumed_the_budget__is_allowed() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    invoice_a = budget_setup.an_unsaved_invoice_with_assignment(Money("600", EUR), budget)
    invoice_service.save(invoice_a)
    budget_setup.an_invoice_with_assignment(Money("400", EUR), budget)
    balance_before = budget_query.budget_balances(budget_id)

    # Invoice A's 600 were committed before B; re-saving A (edit) re-checks
    # only the change over its own commitment, not the whole amount.
    invoice_service.save(invoice_a)

    # The budget is fully committed — a fresh commitment is rejected — yet the
    # re-save of A went through and changed nothing.
    assert budget_query.budget_balances(budget_id) == balance_before
    with pytest.raises(budget_service.BudgetCapacityExceededError):
        budget_service.ensure_capacity(budget_id, Money("1", EUR))


@pytest.mark.django_db
def test__re_saving_invoice__with_raised_assignment_beyond_capacity__is_rejected() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    invoice_a = budget_setup.an_unsaved_invoice_with_assignment(Money("600", EUR), budget)
    invoice_service.save(invoice_a)
    budget_setup.an_invoice_with_assignment(Money("400", EUR), budget)

    # Edit: raise invoice A's assignment to 700 — the +100 delta is a new
    # commitment, and the budget no longer has room for it.
    edited = budget_setup.an_unsaved_invoice_with_assignment(Money("700", EUR), budget)
    edited.id = invoice_a.id

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        invoice_service.save(edited)

    # Nothing persisted: reserved stays at 600 + 400, and the ledger holds
    # only A's commitment row (B is seeded through the repository).
    assert budget_query.budget_balances(budget_id).reserved == Money("1000", EUR)
    assert BudgetLedgerEntry.objects.count() == 1


@pytest.mark.django_db
def test__saving_invoice_with_over_capacity_assignment__is_rejected() -> None:
    budget, _ = budget_setup.a_budget(amount=Money("1000", EUR))
    position = invoice_positions.create(
        item=FreeItem("APC", cost_type=PublicationCostType.Gold_OA),
        cost=Money("2000", EUR),
        tax_rate=TaxRate.from_percentage(0),
        external_position_id="POS-1",
    )
    position.assign_funding(budget, Decimal(2000))
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        invoice_service.save(invoice)

    assert invoice_repository.first() is None
    # The rejected commitment books nothing: no ledger row on the budget.
    assert BudgetLedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test__exhausted_budget__ensure_capacity__raises_capacity_exceeded() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("10000", EUR), budget, paid=True)

    with pytest.raises(budget_service.BudgetCapacityExceededError) as excinfo:
        budget_service.ensure_capacity(budget_id, Money("1", EUR))

    assert "DARK 2026" in str(excinfo.value)
    assert "1" in str(excinfo.value)


@pytest.mark.django_db
def test__available_funds_transfer__books_debit_on_source_and_credited_on_target() -> None:
    _, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    budget_service.create_transfer(source_id, target_id, Money("2000", EUR), "top-up")

    source_balance = budget_query.budget_balances(source_id)
    assert source_balance.debit == Money("2000", EUR)
    assert source_balance.available == Money("3000", EUR)

    target_balance = budget_query.budget_balances(target_id)
    assert target_balance.credited == Money("2000", EUR)
    assert target_balance.available == Money("12000", EUR)


@pytest.mark.django_db
def test__transfer_beyond_source_capacity__is_rejected_and_not_persisted() -> None:
    _, source_id = budget_setup.a_budget(name="Source", amount=Money("1000", EUR))
    _, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))
    balance_before = budget_query.budget_balances(source_id)

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        budget_service.create_transfer(source_id, target_id, Money("1001", EUR), "too much")

    # Nothing booked: the source balance is untouched, no transfer row, no
    # ledger rows on either budget.
    assert budget_query.budget_balances(source_id) == balance_before
    assert BudgetTransfer.objects.count() == 0
    assert BudgetLedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test__add_funds_in_foreign_currency__is_rejected() -> None:
    """Transfers carry a bare decimal counted in the budget's currency — a
    foreign-currency amount would be silently mis-scaled on read."""
    _, budget_id = budget_setup.a_budget(name="Target", amount=Money("5000", EUR))

    with pytest.raises(budget_service.InvalidTransfer):
        budget_service.add_funds(budget_id, Money("500", USD), "grant top-up")

    assert BudgetTransfer.objects.count() == 0
    assert BudgetLedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test__debt_transfer_from_exceeded_budget__books_debit_on_target_only() -> None:
    _source, source_id = budget_setup.a_budget(name="Exceeded", amount=Money("1000", EUR))
    _, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("1200", EUR), _source, paid=True)

    budget_service.create_transfer(source_id, target_id, Money("-200", EUR), "overrun")

    source_balance = budget_query.budget_balances(source_id)
    assert source_balance.debit == Money("0", EUR)
    assert source_balance.spent == Money("1200", EUR)
    assert source_balance.available == Money("-200", EUR)  # source stays exceeded

    target_balance = budget_query.budget_balances(target_id)
    assert target_balance.debit == Money("200", EUR)
    assert target_balance.credited == Money("0", EUR)
    assert target_balance.available == Money("9800", EUR)


@pytest.mark.django_db
def test__transfer_to_non_budget_funding_source__is_rejected() -> None:
    _, budget_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    institution = modelfactory.institution()
    split = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    split.id = funding_source_repository.create(split)

    with pytest.raises(budget_service.InvalidTransfer):
        budget_service.create_transfer(budget_id, split.id, Money("100", EUR), "")

    assert BudgetTransfer.objects.count() == 0
    # A rejected transfer books nothing on either budget.
    assert BudgetLedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test__transfer_in_foreign_currency__is_rejected() -> None:
    _, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _, target_id = budget_setup.a_budget(name="Target", amount=Money("5000", EUR))

    with pytest.raises(budget_service.InvalidTransfer):
        budget_service.create_transfer(source_id, target_id, Money("100", USD), "")

    assert BudgetTransfer.objects.count() == 0
    # A rejected transfer books nothing on either budget.
    assert BudgetLedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test__transfer_between_budgets_in_different_currencies__is_rejected() -> None:
    _, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _, target_id = budget_setup.a_budget(name="Target", amount=Money("5000", USD))

    with pytest.raises(budget_service.InvalidTransfer):
        budget_service.create_transfer(source_id, target_id, Money("100", EUR), "")

    assert BudgetTransfer.objects.count() == 0
    # A rejected transfer books nothing on either budget.
    assert BudgetLedgerEntry.objects.count() == 0
