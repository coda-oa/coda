from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client
from pytest_django import DjangoDbBlocker

from coda.apps.users.models import User

BASE_DIR = Path(__file__).parent.parent


@pytest.fixture
def logged_in(client: Client) -> None:
    client.force_login(User.objects.create_user("testuser"))


@pytest.fixture(autouse=True, scope="module")
def populate_database(django_db_blocker: DjangoDbBlocker) -> None:
    with django_db_blocker.unblock():
        fixtures = list((BASE_DIR / "config/fixtures").glob("*.json"))
        call_command("loaddata", *fixtures)
