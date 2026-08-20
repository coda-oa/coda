from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.invoices.models import FundingSource
from coda.domain.finance.invoice import PaymentStatus
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.invoices.funding_helpers import create_assignment


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__context_contains_budget_summary(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    funding_source.budget_amount = Decimal("50000.00")
    funding_source.save()
    create_assignment(
        funding_source,
        Decimal("100.00"),
        "EUR",
        modelfactory.invoice(),
        status=PaymentStatus.Paid.value,
    )
    create_assignment(funding_source, Decimal("50.00"), "EUR", modelfactory.invoice())

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    assert response.status_code == 200
    assert response.context["budget_total"] == Money(50000, Currency.EUR)
    assert response.context["spent"] == Money(100, Currency.EUR)
    assert response.context["reserved"] == Money(50, Currency.EUR)
    assert response.context["remaining"] == Money(49850, Currency.EUR)
    assert response.context["is_budget"] is True
    assert response.context["home_currency"] == Currency.EUR


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__without_budget_amount_has_no_bar_values(client: Client) -> None:
    funding_source = modelfactory.budget("No budget")

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    assert response.status_code == 200
    assert response.context["is_budget"] is True
    assert "budget_total" not in response.context
    assert "remaining" not in response.context


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__institution_source_has_no_budget_values(client: Client) -> None:
    institution = modelfactory.institution()
    funding_source = FundingSource.objects.create(
        type="institution", institution=institution, name=institution.name
    )
    create_assignment(funding_source, Decimal("42.00"), "EUR", modelfactory.invoice())

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    assert response.status_code == 200
    assert "is_budget" not in response.context
    assert "budget_total" not in response.context
    assert response.context["reserved"] == Money(42, Currency.EUR)
    assert len(response.context["invoices"]) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__shows_budget_total_in_header(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    funding_source.budget_amount = Decimal("50000.00")
    funding_source.save()

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "50000.00 EUR" in content
    assert "€50,000.00" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__renders_budget_bar_with_actual_css_variables(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    funding_source.budget_amount = Decimal("50000.00")
    funding_source.save()
    create_assignment(
        funding_source,
        Decimal("16000.00"),
        "EUR",
        modelfactory.invoice(),
        status=PaymentStatus.Paid.value,
    )
    create_assignment(funding_source, Decimal("4000.00"), "EUR", modelfactory.invoice())

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "--total: 50000.00" in content
    assert "--spent: 16000.00" in content
    assert "--reserved: 4000.00" in content
    assert "--remaining: 30000.00" in content
    assert "INV-2026-001" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__renders_legend_with_real_amounts(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    funding_source.budget_amount = Decimal("50000.00")
    funding_source.save()
    create_assignment(
        funding_source,
        Decimal("16000.00"),
        "EUR",
        modelfactory.invoice(),
        status=PaymentStatus.Paid.value,
    )
    create_assignment(funding_source, Decimal("4000.00"), "EUR", modelfactory.invoice())

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "Remaining: 30000.00 EUR" in content
    assert "Spent: 16000.00 EUR" in content
    assert "Reserved: 4000.00 EUR" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__shows_invoice_table_totals(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    funding_source.budget_amount = Decimal("50000.00")
    funding_source.save()
    create_assignment(
        funding_source,
        Decimal("16000.00"),
        "EUR",
        modelfactory.invoice(),
        status=PaymentStatus.Paid.value,
    )
    create_assignment(funding_source, Decimal("4000.00"), "EUR", modelfactory.invoice())

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "Total Spent:" in content
    assert "Total Reserved:" in content
    assert "Remaining Budget:" in content
    assert "<strong>16000.00 EUR</strong>" in content
    assert "<strong>4000.00 EUR</strong>" in content
    assert "<strong>30000.00 EUR</strong>" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__lists_related_invoices_with_status(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    paid_invoice = modelfactory.invoice()
    unpaid_invoice = modelfactory.invoice()
    rejected_invoice = modelfactory.invoice()
    create_assignment(
        funding_source, Decimal("100.00"), "EUR", paid_invoice, status=PaymentStatus.Paid.value
    )
    create_assignment(
        funding_source, Decimal("50.00"), "EUR", unpaid_invoice, status=PaymentStatus.Unpaid.value
    )
    create_assignment(
        funding_source,
        Decimal("25.00"),
        "EUR",
        rejected_invoice,
        status=PaymentStatus.Rejected.value,
    )

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert paid_invoice.number in content
    assert unpaid_invoice.number in content
    assert rejected_invoice.number in content
    assert "100.00 EUR" in content
    assert ">Paid</small>" in content
    assert ">Reserved</small>" in content
    assert ">not included (invoice rejected)</small>" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__shows_hint_instead_of_bar_without_budget_amount(client: Client) -> None:
    funding_source = modelfactory.budget("No budget")

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "Set a total budget to see the budget overview." in content
    assert "budget-bar" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__institution_source_shows_invoices_without_budget_bar(
    client: Client,
) -> None:
    institution = modelfactory.institution()
    funding_source = FundingSource.objects.create(
        type="institution", institution=institution, name=institution.name
    )
    invoice = modelfactory.invoice()
    create_assignment(funding_source, Decimal("42.00"), "EUR", invoice)

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "budget-bar" not in content
    assert "Total Budget" not in content
    assert invoice.number in content
    assert "42.00 EUR" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__shows_warning_for_unconvertible_invoices(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")
    funding_source.budget_amount = Decimal("1000.00")
    funding_source.save()
    usd_invoice = modelfactory.invoice()
    create_assignment(funding_source, Decimal("100.00"), "USD", usd_invoice)
    create_assignment(funding_source, Decimal("10.00"), "EUR", modelfactory.invoice())

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "Not included in the totals (no conversion to EUR)" in content
    assert usd_invoice.number in content
    assert "100.00 USD" in content
    assert content.count(usd_invoice.number) == 1
    assert "Remaining: 990.00 EUR" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__detail_view__shows_empty_state_without_invoices(client: Client) -> None:
    funding_source = modelfactory.budget("Empty")

    response = client.get(
        reverse("invoices:fundingsource_detail", kwargs={"pk": funding_source.pk})
    )

    content = response.content.decode()
    assert "No invoices are assigned to this funding source yet." in content
