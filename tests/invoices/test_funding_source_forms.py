from decimal import Decimal

from django.test import Client
import pytest
from django.urls import reverse

from coda.apps.invoices.models import FundingSource
from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_create_form__on_submit__saves_budget_amount(client: Client) -> None:
    response = client.post(
        reverse("invoices:fundingsource_create"),
        {"name": "EU Horizon", "budget_amount": "50000.00"},
    )

    funding_source = FundingSource.objects.get(name="EU Horizon")

    assert response.status_code == 302
    assert funding_source.budget_amount == Decimal("50000.00")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_update_form__on_submit__saves_budget_amount(client: Client) -> None:
    funding_source = modelfactory.budget("EU Horizon")

    response = client.post(
        reverse("invoices:fundingsource_update", kwargs={"pk": funding_source.pk}),
        {"name": "EU Horizon", "budget_amount": "75000.00"},
    )

    funding_source.refresh_from_db()

    assert response.status_code == 302
    assert funding_source.budget_amount == Decimal("75000.00")
