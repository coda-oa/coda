from typing import cast

from django.http import HttpResponse
from django.urls import reverse
import pytest
from django.test import Client
from tests import modelfactory
from tests.opencost.helpers import (
    assert_current_filter,
    assert_current_filters,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_processing_status(client: Client) -> None:
    response = get_export_create_response(client, processing_status=["open", "approved", "closed"])
    assert_current_filters(response, processing_status=["open", "approved", "closed"])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_multiple_publication_states(client: Client) -> None:
    response = get_export_create_response(client, publication_states=["Published", "Submitted"])
    assert_current_filters(response, publication_states=["Published", "Submitted"])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_publication_states(client: Client) -> None:
    response = get_export_create_response(client, publication_states=["Published"])
    assert_current_filters(response, publication_states=["Published"])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_publication_type(client: Client) -> None:
    response = get_export_create_response(client, publication_type=["article"])
    assert_current_filter(response, "publication_type", "article")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_payment_methods(client: Client) -> None:
    response = get_export_create_response(client, payment_methods=["direct", "reimbursement"])
    assert_current_filters(response, payment_methods=["direct", "reimbursement"])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_open_access_type(client: Client) -> None:
    response = get_export_create_response(client, open_access_type=["Gold", "Hybrid"])
    assert_current_filters(response, open_access_type=["Gold", "Hybrid"])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_payment_status(client: Client) -> None:
    response = get_export_create_response(client, payment_status=["paid", "unpaid"])
    assert_current_filters(response, payment_status=["paid", "unpaid"])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_funding_source(client: Client) -> None:
    budget = modelfactory.budget(name="Test Budget")
    response = get_export_create_response(client, funding_source=[str(budget.pk)])
    assert_current_filter(response, "funding_source", str(budget.pk))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_contract_name(client: Client) -> None:
    contract = modelfactory.contract()
    response = get_export_create_response(client, contract_name=[str(contract.pk)])
    assert_current_filter(response, "contract_name", str(contract.pk))


def get_export_create_response(client: Client, **filters: str | list[str]) -> HttpResponse:
    return cast(HttpResponse, client.get(reverse("exports:fundingrequests_csv_create"), filters))
