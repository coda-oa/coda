from decimal import Decimal

import pytest
from django.db import models

from coda.apps.invoices.models import BudgetLedgerEntry, BudgetTransfer
from coda.contexts.finance.services import budget_service, invoice_service
from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto, UpdateReviewDto
from coda.contexts.fundingrequest.services import fundingrequests as fr_services
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import Invoice
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.invoices import budget_setup

EUR = Currency.EUR
USD = Currency.USD


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
def test__re_approving_review__appends_a_further_row_instead_of_updating() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2000))
    )
    fr_services.update_review(
        FundingRequestId(funding_request.pk), review_dto(budget_id, Decimal(2000))
    )

    assert ledger(budget_id).filter(event="commitment").count() == 2


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
