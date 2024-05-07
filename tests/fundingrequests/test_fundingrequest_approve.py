import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.fundingrequest import FundingRequestId, Review
from tests import factory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funding_request_approve_view__approves_request(client: Client) -> None:
    request = factory.fundingrequest()

    client.post(reverse("fundingrequests:approve"), {"fundingrequest": request.pk})

    assert_approved(FundingRequestId(request.pk))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funding_request_reject_view__rejects_request(client: Client) -> None:
    request = factory.fundingrequest()

    client.post(reverse("fundingrequests:reject"), {"fundingrequest": request.pk})

    id = FundingRequestId(request.pk)
    assert_rejected(id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funding_request_open_view__rejects_request(client: Client) -> None:
    request = factory.fundingrequest()

    client.post(reverse("fundingrequests:open"), {"fundingrequest": request.pk})

    id = FundingRequestId(request.pk)
    assert_open(id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize("view_name", ["approve", "reject"])
def test__approving_or_requesting_request__redirects_to_funding_request_detail(
    client: Client, view_name: str
) -> None:
    request = factory.fundingrequest()

    response = client.post(reverse(f"fundingrequests:{view_name}"), {"fundingrequest": request.pk})

    assert response.status_code == 302
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": request.pk}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize("view_name", ["approve", "reject"])
def test__approving_or_requesting_non_existent_request__raises_404(
    client: Client, view_name: str
) -> None:
    response = client.post(reverse(f"fundingrequests:{view_name}"), {"fundingrequest": 1})
    assert response.status_code == 404


def assert_approved(id: FundingRequestId) -> None:
    assert repository.get_by_id(id).review() == Review.Approved


def assert_rejected(id: FundingRequestId) -> None:
    assert repository.get_by_id(id).review() == Review.Rejected


def assert_open(id: FundingRequestId) -> None:
    assert repository.get_by_id(id).review() == Review.Open
