import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.test import Client
from playwright.sync_api import Page, sync_playwright
from pytest_django import DjangoDbBlocker
from pytest_django.live_server_helper import LiveServer

from coda.apps.users.models import User

BASE_DIR = Path(__file__).parent.parent


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "ui_test: mark test as requiring a browser")


def pytest_runtest_setup(item: pytest.Item) -> None:
    if (
        isinstance(item, pytest.Function)
        and "coda_page" in item.fixturenames
        and item.get_closest_marker("ui_test") is None
    ):
        pytest.fail("coda_page fixture requires the @pytest.mark.ui_test marker")


@pytest.fixture(scope="session")
def _browser_context(live_server: LiveServer) -> Generator[tuple[Page, LiveServer]]:
    """
    Session-scoped browser context for performance.

    Creates a single browser instance shared across all UI tests.
    Individual tests handle authentication separately.
    """
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chromium")
        context = browser.new_context()
        page = context.new_page()

        yield page, live_server

        browser.close()


@pytest.fixture
def coda_page(
    _browser_context: tuple[Page, LiveServer],
    django_db_blocker: DjangoDbBlocker,
) -> Generator[Page]:
    """
    Function-scoped fixture that provides an authenticated Playwright page.

    Reuses the session-scoped browser (fast!) but authenticates fresh for each test
    to avoid database rollback issues. Best of both worlds!
    """
    page, _ = _browser_context

    # Create fresh user for this test
    with django_db_blocker.unblock():
        # Clean up any existing test users to avoid conflicts
        User.objects.filter(username="superuser").delete()
        user = User.objects.create_superuser("superuser", password="superuser_password")

        # Create new session
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()

    # Update cookies for this test (reuses existing browser!)
    page.context.clear_cookies()
    page.context.add_cookies(
        [
            {
                "name": "sessionid",
                "value": str(session.session_key),
                "domain": "localhost",
                "path": "/",
            }
        ]
    )

    yield page

    # Cleanup: clear cookies for next test
    page.context.clear_cookies()


@pytest.fixture
def logged_in(client: Client) -> None:
    client.force_login(User.objects.create_user("testuser"))


@pytest.fixture(autouse=True, scope="session")
def populate_database(django_db_setup: Any, django_db_blocker: DjangoDbBlocker) -> None:
    with django_db_blocker.unblock():
        fixtures = list((BASE_DIR / "config/fixtures").glob("*.json"))
        call_command("loaddata", *fixtures)


@pytest.fixture(autouse=True)
def media_root(settings: Any, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
