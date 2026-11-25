import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse

from coda.apps.invoices.models import FundingSource


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funding_source__redirects_to_list_and_flashes_named_success(
    client: Client,
) -> None:
    response = client.post(
        reverse("invoices:fundingsource_create"),
        {"name": "New Budget"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("invoices:fundingsource_list")
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Funding source 'New Budget' created successfully."
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funding_source__redirects_to_list_and_flashes_named_success(
    client: Client,
) -> None:
    funding_source = FundingSource.objects.create(name="Old Budget")

    response = client.post(
        reverse("invoices:fundingsource_update", kwargs={"pk": funding_source.pk}),
        {"name": "Renamed Budget"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("invoices:fundingsource_list")
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Funding source 'Renamed Budget' updated successfully."
    ]
