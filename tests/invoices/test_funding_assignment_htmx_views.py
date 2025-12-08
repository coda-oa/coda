import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.contexts.finance.dto.edit_position_dtos import PositionDto, PositionList
from coda.contexts.finance.services import invoice_parser
from coda.domain.money import Currency
from tests import domainfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_initial_assignment__assigns_all_costs_to_new_assignment(client: Client) -> None:
    position = domainfactory.free_position(Currency.EUR)
    dto = invoice_parser.position_to_dto(position)

    response = client.post(
        reverse("invoices:position_add_funding_assignment"),
        formdata.map_to_dict(PositionList(positions=[dto]))
        | {"position_index": "1", "currency": Currency.EUR.code},
    )

    actual: PositionDto = response.context["position"]
    assert len(actual.funding_assignments) == 1
    assert actual.funding_assignments[0].amount == position.cost.amount
