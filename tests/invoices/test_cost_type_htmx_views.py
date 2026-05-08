from django.test import Client
from django.urls import reverse
import pytest

from coda.domain.finance.costtypes import PublicationCostType


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__changing_cost_type_to_vat__has_no_tax_rate_field(client: Client) -> None:
    response = client.get(
        reverse("invoices:position_cost_type_options"),
        data={"counter": "1", "positions-1-item-cost_type": PublicationCostType.Vat.value},
    )

    assert response.content == b""


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__changing_cost_type__keeps_entered_tax_rate(client: Client) -> None:
    response = client.get(
        reverse("invoices:position_cost_type_options"),
        data={
            "counter": "1",
            "positions-1-item-cost_type": PublicationCostType.Publication_Charge.value,
            "positions-1-tax_rate": "85",
        },
    )

    assert response.context["tax_rate"] == "85"
