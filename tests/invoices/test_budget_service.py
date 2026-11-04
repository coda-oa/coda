from decimal import Decimal

import pytest

from coda.apps.invoices import budget_query
from coda.apps.invoices import repository as invoice_repository
from coda.contexts.finance.services import budget_service, invoice_service
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

    budget_service.ensure_capacity(budget_id, Money("5000", EUR))


@pytest.mark.django_db
def test__foreign_currency_commitment__is_invisible_to_the_capacity_check() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    budget_setup.an_invoice_with_assignment(Money("1000", EUR), budget, paid=True)

    budget_service.ensure_capacity(budget_id, Money("5000", USD))  # rate-pending: not checked


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
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _target, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    budget_service.create_transfer(source_id, target_id, Money("2000", EUR), "top-up")

    source_balance = budget_query.budget_balances(source_id)
    assert source_balance.debit == Money("2000", EUR)
    assert source_balance.available == Money("3000", EUR)

    target_balance = budget_query.budget_balances(target_id)
    assert target_balance.credited == Money("2000", EUR)
    assert target_balance.available == Money("12000", EUR)


@pytest.mark.django_db
def test__transfer_beyond_source_capacity__is_rejected_and_not_persisted() -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("1000", EUR))
    _target, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        budget_service.create_transfer(source_id, target_id, Money("1001", EUR), "too much")

    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 0


@pytest.mark.django_db
def test__debt_transfer_from_exceeded_budget__books_debit_on_target_only() -> None:
    _source, source_id = budget_setup.a_budget(name="Exceeded", amount=Money("1000", EUR))
    _target, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))
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
    from coda.apps.invoices.models import BudgetTransfer
    from coda.apps.invoices import funding_source_repository
    from coda.domain.author import InstitutionId

    budget, budget_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    institution = modelfactory.institution()
    split = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    split.id = funding_source_repository.create(split)

    with pytest.raises(budget_service.InvalidTransfer):
        budget_service.create_transfer(budget_id, split.id, Money("100", EUR), "")

    assert BudgetTransfer.objects.count() == 0


@pytest.mark.django_db
def test__transfer_in_foreign_currency__is_rejected() -> None:
    source, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    target, target_id = budget_setup.a_budget(name="Target", amount=Money("5000", EUR))

    with pytest.raises(budget_service.InvalidTransfer):
        budget_service.create_transfer(source_id, target_id, Money("100", USD), "")

    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 0
