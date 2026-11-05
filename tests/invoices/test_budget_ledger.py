from decimal import Decimal

import pytest
from django.db import models

from coda.apps.invoices.models import BudgetLedgerEntry, BudgetTransfer
from coda.contexts.finance.services import budget_service, invoice_service
from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto, UpdateReviewDto
from coda.contexts.fundingrequest.services import fundingrequests as fr_services
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import Invoice
from coda.domain.finance.taxrate import TaxRate
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.invoices import budget_setup

EUR = Currency.EUR
USD = Currency.USD


@pytest.mark.django_db
def test__taxed_assignment__ledger_books_gross_in_original_currency() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    invoice = budget_setup.an_unsaved_invoice_with_assignment(
        Money("1680.6723", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )

    invoice_service.save(invoice)

    row = ledger(budget_id).get()
    assert row.event == "commitment"
    assert row.amount == Decimal("2000.00")  # net 1680.6723 × 1.19, rounded
    assert row.currency == "EUR"


@pytest.mark.django_db
def test__taxed_assignment__paying_books_gross_payment_row() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    invoice = budget_setup.an_unsaved_invoice_with_assignment(
        Money("1680.6723", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )
    invoice_id = invoice_service.save(invoice)

    invoice_service.pay_invoice(invoice_id)

    row = ledger(budget_id).filter(event="payment").get()
    assert row.amount == Decimal("2000.00")
    assert row.currency == "EUR"


@pytest.mark.django_db
def test__re_saving_taxed_assignment__delta_is_gross_of_tax() -> None:
    """The capacity delta compares gross-of-tax amounts on both sides: A holds
    gross 2000, B holds gross 952 of a 3000 budget. Raising A to gross 2050 is
    a +50 delta against 48 available — rejected. A net-basis delta (42.02)
    would wrongly allow it."""
    budget, _ = budget_setup.a_budget(amount=Money("3000", EUR))
    invoice_a = budget_setup.an_unsaved_invoice_with_assignment(
        Money("1680.6723", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )
    invoice_service.save(invoice_a)
    budget_setup.an_invoice_with_assignment(
        Money("800", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )

    edited = budget_setup.an_unsaved_invoice_with_assignment(
        Money("1722.69", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )
    edited.id = invoice_a.id

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        invoice_service.save(edited)


def review_dto(budget_id: int, amount: Decimal) -> UpdateReviewDto:
    return UpdateReviewDto(
        decided_funding_amount=amount,
        decided_funding_currency="EUR",
        reviewer_remarks="",
        result="approved",
        funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=amount)],
    )


def ledger(budget_id: int) -> models.QuerySet[BudgetLedgerEntry]:
    return BudgetLedgerEntry.objects.filter(budget_id=budget_id)


def usd_invoice_assigned_to(budget: "Budget") -> Invoice:
    return budget_setup.an_unsaved_invoice_with_assignment(Money("3000", USD), budget)


@pytest.mark.django_db
def test__approving_review_with_split__appends_commitment_row() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2000))
    )

    row = ledger(budget_id).get()
    assert row.event == "commitment"
    assert row.amount == Decimal(2000)
    assert row.currency == "EUR"
    assert row.review_split is not None
    assert row.funding_assignment is None


@pytest.mark.django_db
def test__re_approving_review__with_changed_split__appends_a_further_row() -> None:
    """A *changed* re-approval books a further commitment row; an unchanged
    re-approval books none (the ledger must not drift on untouched re-saves)."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2000))
    )
    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2500))
    )

    amounts = list(
        ledger(budget_id).filter(event="commitment").values_list("amount", flat=True)
    )
    assert amounts == [Decimal(2000), Decimal(2500)]


@pytest.mark.django_db
def test__re_approving_review__unchanged_splits__books_no_further_row() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2000))
    )
    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2000))
    )

    assert ledger(budget_id).filter(event="commitment").count() == 1


@pytest.mark.django_db
def test__saving_invoice_with_assignment__appends_commitment_row_in_original_currency() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    invoice = usd_invoice_assigned_to(_budget)

    invoice_id = invoice_service.save(invoice)

    row = ledger(budget_id).get()
    assert row.event == "commitment"
    assert row.amount == Decimal(3000)
    assert row.currency == "USD"
    assert row.funding_assignment is not None
    assert row.funding_assignment.position.invoice_id == invoice_id


@pytest.mark.django_db
def test__re_saving_invoice__does_not_book_a_further_commitment_ledger_row() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    invoice = budget_setup.an_unsaved_invoice_with_assignment(Money("600", EUR), budget)

    invoice_service.save(invoice)
    invoice_service.save(invoice)

    assert ledger(budget_id).filter(event="commitment").count() == 1


@pytest.mark.django_db
def test__paying_invoice__appends_payment_row_in_original_currency() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    invoice = usd_invoice_assigned_to(_budget)
    invoice_id = invoice_service.save(invoice)

    invoice_service.pay_invoice(invoice_id)

    payment_rows = ledger(budget_id).filter(event="payment")
    assert payment_rows.count() == 1
    row = payment_rows.get()
    assert row.amount == Decimal(3000)
    assert row.currency == "USD"
    assert row.funding_assignment is not None


@pytest.mark.django_db
def test__transfer__appends_rows_for_both_budgets() -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _target, target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    budget_service.create_transfer(source_id, target_id, Money("2000", EUR), "top-up")

    transfer_rows = BudgetLedgerEntry.objects.filter(event="transfer")
    assert transfer_rows.count() == 2
    assert {row.budget_id for row in transfer_rows} == {source_id, target_id}
    assert all(row.amount == Decimal(2000) for row in transfer_rows)
    assert all(row.transfer is not None for row in transfer_rows)
    assert BudgetTransfer.objects.count() == 1
