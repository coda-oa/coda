import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test__login_view__anonymous__shows_login_page(client: Client) -> None:
    response = client.get(reverse("login"))

    assert response.status_code == 200


@pytest.mark.django_db
def test__login_view__authenticated__redirects_to_home(client: Client) -> None:
    client.force_login(get_user_model().objects.create_user("testuser"))

    response = client.get(reverse("login"))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("home")
