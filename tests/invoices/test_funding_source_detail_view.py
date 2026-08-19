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
