from django.test import Client
import pytest

from coda.apps.users.models import User


@pytest.fixture
def logged_in(client: Client) -> None:
    client.force_login(User.objects.create_user("testuser"))
