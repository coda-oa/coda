"""Tests for the Update from ROR view (modal + POST handler)."""

import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse

from coda.domain.institution.links import Ror
from tests import modelfactory
from tests.fundingorganizations.conftest import BMFTR_NAME, update_from_ror


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
class TestUpdateFromRorPost:
    """Tests for the POST handler that performs the ROR update."""

    def test__updates_organization_name(self, client: Client) -> None:
        old_name = "Bundesministerium für Bildung und Forschung"
        org = modelfactory.funding_organization(name=old_name)
        org.set_links([Ror("https://ror.org/04pz7b180")])
        org.save()

        update_from_ror(client, org.pk)

        org.refresh_from_db()
        assert org.name == BMFTR_NAME

    def test__adds_success_message(self, client: Client) -> None:
        org = modelfactory.funding_organization(name="Test Funder")
        org.set_links([Ror("https://ror.org/04pz7b180")])
        org.save()

        response = update_from_ror(client, org.pk)

        messages_list = list(get_messages(response.wsgi_request))
        assert any("updated from ROR" in msg.message for msg in messages_list)

    def test__success_message_uses_updated_name(self, client: Client) -> None:
        old_name = "Bundesministerium für Bildung und Forschung"
        org = modelfactory.funding_organization(name=old_name)
        org.set_links([Ror("https://ror.org/04pz7b180")])
        org.save()

        response = update_from_ror(client, org.pk)

        messages_list = list(get_messages(response.wsgi_request))
        assert any(BMFTR_NAME in msg.message for msg in messages_list)

    def test__redirects_to_detail_page(self, client: Client) -> None:
        org = modelfactory.funding_organization(name="Test Funder")
        org.set_links([Ror("https://ror.org/04pz7b180")])
        org.save()

        response = update_from_ror(client, org.pk)

        expected_url = reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk})
        assert response["HX-Redirect"] == expected_url


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in", "inject_failing_ror_client")
class TestUpdateFromRorFailure:
    """Tests for error handling when the ROR API is unavailable."""

    def test__adds_error_message(self, client: Client) -> None:
        org = modelfactory.funding_organization(name="Test Funder")

        response = update_from_ror(client, org.pk)

        messages_list = list(get_messages(response.wsgi_request))
        assert any("Error" in msg.message for msg in messages_list)

    def test__redirects_to_detail_page(self, client: Client) -> None:
        org = modelfactory.funding_organization(name="Test Funder")

        response = update_from_ror(client, org.pk)

        expected_url = reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk})
        assert response["HX-Redirect"] == expected_url
