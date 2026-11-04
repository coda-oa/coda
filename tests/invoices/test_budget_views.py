from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.invoices import budget_query
from coda.domain.money import Currency, Money
from tests.invoices import budget_setup

EUR = Currency.EUR


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_list__shows_status_chip_and_available(client: Client) -> None:
    budget, _ = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)
    exceeded, _ = budget_setup.a_budget(name="Overdrawn", amount=Money("1000", EUR))
    budget_setup.an_invoice_with_assignment(Money("1200", EUR), exceeded, paid=True)

    response = client.get(reverse("invoices:fundingsource_list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "DARK 2026" in content
    assert "Overdrawn" in content
    assert "within budget" in content
    assert "exceeded" in content
    assert "7500" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__shows_full_state_and_ledger(client: Client) -> None:
    budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "DARK 2026" in content
    assert "10000" in content  # amount
    assert "2500" in content  # spent
    assert "7500" in content  # available
    assert "Period:" in content
    assert "2026" in content  # period year
    assert "ledger" in content.lower()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_transfer__books_transfer_and_shows_in_balances(client: Client) -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _target, _target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    response = client.post(
        reverse("invoices:budget_transfer", kwargs={"pk": source_id}),
        {"target": str(_target.id), "amount": "2000", "provenance_note": "top-up"},
    )

    assert response.status_code == 302
    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 1
    assert budget_query.budget_balances(source_id).debit == Money("2000", EUR)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_transfer__beyond_capacity__renders_error(client: Client) -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("1000", EUR))
    _target, _target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    response = client.post(
        reverse("invoices:budget_transfer", kwargs={"pk": source_id}),
        {"target": str(_target.id), "amount": "1001", "provenance_note": ""},
    )

    assert response.status_code == 200
    assert b"exceeds its capacity" in response.content
    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_transfer__garbage_amount__renders_error_and_books_nothing(client: Client) -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("1000", EUR))
    _target, _target_id = budget_setup.a_budget(name="Target", amount=Money("1000", EUR))

    response = client.post(
        reverse("invoices:budget_transfer", kwargs={"pk": source_id}),
        {"target": str(_target_id), "amount": "abc", "provenance_note": ""},
    )

    assert response.status_code == 200
    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_create__with_full_attributes__persists_budget(client: Client) -> None:
    from coda.apps.invoices.models import FundingSource

    response = client.post(
        reverse("invoices:fundingsource_create"),
        {
            "name": "DARK 2026",
            "budget_amount": "10000",
            "budget_currency": "EUR",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "allow_over": "on",
            "allowance_amount": "5000",
        },
    )

    assert response.status_code == 302
    budget = FundingSource.objects.get(name="DARK 2026")
    assert budget.budget_amount == Decimal(10000)
    assert budget.budget_currency == "EUR"
    assert str(budget.period_start) == "2026-01-01"
    assert str(budget.period_end) == "2026-12-31"
    assert budget.allow_over is True
    assert budget.allowance_amount == Decimal(5000)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_create__blank_terms__renders_field_errors_and_persists_nothing(
    client: Client,
) -> None:
    from coda.apps.invoices.models import FundingSource

    response = client.post(
        reverse("invoices:fundingsource_create"),
        {"name": "DARK 2026"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "required" in content
    assert not FundingSource.objects.filter(name="DARK 2026").exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_update__amount_after_period_start__cannot_be_changed(client: Client) -> None:
    _budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))

    response = client.post(
        reverse("invoices:fundingsource_update", kwargs={"pk": budget_id}),
        {
            "name": "DARK 2026",
            "budget_amount": "20000",
            "budget_currency": "EUR",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )

    assert response.status_code == 302  # the crafted amount is ignored, not an error
    from coda.apps.invoices.models import FundingSource

    assert FundingSource.objects.get(pk=budget_id).budget_amount == Decimal(10000)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_update__amount_field_is_disabled_after_period_start(client: Client) -> None:
    _budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))

    response = client.get(reverse("invoices:fundingsource_update", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "disabled" in content
    assert "immutable once the period has started" in content
