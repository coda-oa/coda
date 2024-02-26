import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from tests.fundingrequests import factory
from tests.fundingrequests.assertions import assert_correct_funding_request


@pytest.mark.django_db
def test__fundingrequest_wizard__first_step__when_valid_data__redirects_to_next_step(
    client: Client,
) -> None:
    form_data = factory.valid_author_dto(factory.institution().pk)
    response = client.post(reverse("fundingrequests:create"), form_data)

    assertRedirects(response, reverse("fundingrequests:create_journal"))


@pytest.mark.django_db
def test__fundingrequest_wizard__journal_step__when_valid_data__redirects_to_next_step(
    client: Client,
) -> None:
    form_data = {"journal": factory.journal().pk}
    response = client.post(reverse("fundingrequests:create_journal"), form_data)

    assertRedirects(response, reverse("fundingrequests:create_publication"))


@pytest.mark.django_db
def test__fundingrequest_wizard__journal_step__searching_for_journal__shows_search_results(
    client: Client,
) -> None:
    journal = factory.journal()
    response = client.get(
        reverse("fundingrequests:create_journal"), {"journal_title": journal.title}
    )

    assert journal.title in response.content.decode()


@pytest.mark.django_db
def test__fundingrequest_wizard_publication_step__when_valid_data__redirects_to_next_step(
    client: Client,
) -> None:
    form_data = factory.publication_dto()
    response = client.post(reverse("fundingrequests:create_publication"), form_data)

    assertRedirects(response, reverse("fundingrequests:create_funding"))


@pytest.mark.django_db
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
) -> None:
    author = factory.valid_author_dto(factory.institution().pk)
    journal_pk = factory.journal().pk
    journal = {"journal": journal_pk}
    publication = factory.publication_dto()

    funding = factory.funding_dto()

    client.post(reverse("fundingrequests:create"), author)
    client.post(reverse("fundingrequests:create_journal"), journal)
    client.post(reverse("fundingrequests:create_publication"), publication)
    response = client.post(reverse("fundingrequests:create_funding"), funding)

    funding_request = assert_correct_funding_request(author, publication, journal_pk, funding)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))
