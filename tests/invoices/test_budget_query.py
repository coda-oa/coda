from decimal import Decimal

import pytest

from coda.apps.invoices import budget_query
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId
from tests.invoices import budget_setup

EUR = Currency.EUR
USD = Currency.USD


@pytest.mark.django_db
def test__budget_with_paid_assignment__available_is_amount_minus_spent() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)

    actual = budget_query.budget_balances(budget_id)

    assert actual.spent == Money("2500", EUR)
    assert actual.available == Money("7500", EUR)


@pytest.mark.django_db
def test__budget_with_only_unpaid_assignment__nothing_is_spent_yet() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=False)

    actual = budget_query.budget_balances(budget_id)

    assert actual.spent == Money("0", EUR)


@pytest.mark.django_db
def test__assignment_with_tax__reserved_is_gross_of_tax_amount() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("1680.6723", EUR),
        budget,
        paid=False,
        tax_rate=TaxRate.from_percentage(19),
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("2000", EUR)
    assert actual.available == Money("8000", EUR)


@pytest.mark.django_db
def test__vat_type_position__books_exactly_its_cost() -> None:
    """A VAT-type position stores the full cost with tax rate 0; the gross
    expression must not inflate it — the stored rate self-handles."""
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("2000", EUR),
        budget,
        paid=False,
        tax_rate=TaxRate.from_percentage(19),
        cost_type=PublicationCostType.Vat,
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("2000", EUR)
    assert actual.available == Money("8000", EUR)


@pytest.mark.django_db
def test__budget_with_unpaid_assignment__assignment_counts_as_reserved() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=False)

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("2500", EUR)
    assert actual.available == Money("7500", EUR)


@pytest.mark.django_db
def test__foreign_currency_paid_assignment__is_pending_not_spent() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("3000", USD), budget, paid=True)

    actual = budget_query.budget_balances(budget_id)

    assert actual.spent == Money("0", EUR)
    assert actual.pending == (Money("3000", USD),)
    assert actual.available == Money("10000", EUR)


@pytest.mark.django_db
def test__foreign_currency_paid_assignment_with_bank_rate__counts_as_spent_in_budget_currency() -> (
    None
):
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("3000", USD), budget, paid=True, conversion_rate=Decimal("0.9")
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.spent == Money("2700", EUR)  # 3000 USD × 0.9
    assert actual.pending == ()
    assert actual.available == Money("7300", EUR)


@pytest.mark.django_db
def test__pending_conversion__grosses_in_original_currency_then_converts() -> None:
    """A foreign-currency assignment is grossed in its own currency first;
    the bank rate converts the gross amount once, into the budget currency."""
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("2000", USD),
        budget,
        paid=True,
        conversion_rate=Decimal("0.5"),
        tax_rate=TaxRate.from_percentage(19),
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.spent == Money("1190", EUR)  # 2000 USD net → 2380 USD gross → × 0.5
    assert actual.available == Money("8810", EUR)


@pytest.mark.django_db
def test__per_row_rounding__sums_rows_individually() -> None:
    """Each row is rounded to its currency's minor units before summing:
    two rows grossing 1.666 each round to 1.67 (sum 3.34); rounding the sum
    first would give 3.33. The capacity check consumes these figures."""
    budget, budget_id = budget_setup.a_budget(amount=Money("10", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("1.40", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )
    budget_setup.an_invoice_with_assignment(
        Money("1.40", EUR), budget, tax_rate=TaxRate.from_percentage(19)
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("3.34", EUR)
    assert actual.available == Money("6.66", EUR)


@pytest.mark.django_db
def test__budget_with_approved_review_split__split_counts_as_reserved() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = budget_setup.an_approved_funding_request(decided_funding=Money("2000", EUR))
    budget_setup.a_review_split(funding_request, budget, Money("2000", EUR))

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("2000", EUR)
    assert actual.available == Money("8000", EUR)


@pytest.mark.django_db
def test__unpaid_invoice_replaces_decided_funding_in_reserved() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = budget_setup.an_approved_funding_request(decided_funding=Money("2000", EUR))
    budget_setup.a_review_split(funding_request, budget, Money("2000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("2500", EUR),
        budget,
        paid=False,
        publication=PublicationId(funding_request.publication_id),
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("2500", EUR)  # unpaid invoice wins, split dropped
    assert actual.available == Money("7500", EUR)


@pytest.mark.django_db
def test__paying_the_invoice_releases_the_review_reservation() -> None:
    budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = budget_setup.an_approved_funding_request(decided_funding=Money("2000", EUR))
    budget_setup.a_review_split(funding_request, budget, Money("2000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("2500", EUR),
        budget,
        paid=True,
        publication=PublicationId(funding_request.publication_id),
    )

    actual = budget_query.budget_balances(budget_id)

    assert actual.reserved == Money("0", EUR)
    assert actual.spent == Money("2500", EUR)
    assert actual.available == Money("7500", EUR)


def test__budget_with_no_bookings__available_equals_amount() -> None:
    balance = budget_query.BudgetBalance(
        amount=Money("10000", EUR),
        reserved=Money("0", EUR),
        spent=Money("0", EUR),
        credited=Money("0", EUR),
        debit=Money("0", EUR),
    )

    assert balance.available == Money("10000", EUR)
