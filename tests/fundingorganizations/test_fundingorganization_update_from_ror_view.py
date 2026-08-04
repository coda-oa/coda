from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse
from pytest import MonkeyPatch

from coda.apps.fundingrequests.views import funders
from coda.contexts.fundingrequest.services.funder_resolution.ror_client.ror_client import (
    RORClient,
)
from coda.domain.institution.links import Ror
from tests import modelfactory
from tests.contexts.fundingrequest.services.test_ror_client import FakeHttpGet

from tests.fundingorganizations.conftest import BMFTR_NAME


@pytest.fixture
def inject_ror_client(
    bmftr_response_minimal: dict[str, Any],
    monkeypatch: MonkeyPatch,
) -> None:
    fake_client = RORClient(http_client=FakeHttpGet(json_data=bmftr_response_minimal))
    monkeypatch.setattr(funders, "get_ror_client", lambda: fake_client)


@pytest.fixture
def inject_failing_ror_client(monkeypatch: MonkeyPatch) -> None:
    def _raise() -> RORClient:
        raise Exception("ROR API unavailable")

    monkeypatch.setattr(funders, "get_ror_client", _raise)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_from_ror_modal__shows_organization_name(client: Client) -> None:
    org = modelfactory.funding_organization(name="Test Funder")
    response = client.get(
        reverse("fundingrequests:funder_request_update_from_ror", kwargs={"pk": org.pk})
    )
    content = response.content.decode()
    assert "Test Funder" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_from_ror_modal__provides_confirmation_action(client: Client) -> None:
    org = modelfactory.funding_organization(name="Test Funder")
    response = client.get(
        reverse("fundingrequests:funder_request_update_from_ror", kwargs={"pk": org.pk})
    )
    content = response.content.decode()
    expected_url = reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk})
    assert expected_url in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "inject_ror_client")
def test__update_from_ror__updates_organization_name(client: Client) -> None:
    old_name = "Bundesministerium für Bildung und Forschung"
    org = modelfactory.funding_organization(name=old_name)
    org.set_links([Ror("https://ror.org/04pz7b180")])
    org.save()

    client.post(reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk}))

    org.refresh_from_db()
    assert org.name == BMFTR_NAME


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "inject_ror_client")
def test__update_from_ror__adds_success_message(client: Client) -> None:
    org = modelfactory.funding_organization(name="Test Funder")
    org.set_links([Ror("https://ror.org/04pz7b180")])
    org.save()

    response = client.post(reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk}))

    messages_list = list(get_messages(response.wsgi_request))
    assert any("updated from ROR" in msg.message for msg in messages_list)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "inject_ror_client")
def test__update_from_ror__redirects_to_detail_page(client: Client) -> None:
    org = modelfactory.funding_organization(name="Test Funder")
    org.set_links([Ror("https://ror.org/04pz7b180")])
    org.save()

    response = client.post(reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk}))

    expected_url = reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk})
    assert response["HX-Redirect"] == expected_url


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "inject_failing_ror_client")
def test__update_from_ror__on_failure__adds_error_message(client: Client) -> None:
    org = modelfactory.funding_organization(name="Test Funder")

    response = client.post(reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk}))

    messages_list = list(get_messages(response.wsgi_request))
    assert any("Error" in msg.message for msg in messages_list)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "inject_failing_ror_client")
def test__update_from_ror__on_failure__redirects_to_detail_page(client: Client) -> None:
    org = modelfactory.funding_organization(name="Test Funder")

    response = client.post(reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": org.pk}))

    expected_url = reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk})
    assert response["HX-Redirect"] == expected_url
