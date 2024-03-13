from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.forms import PublicationFormData
from coda.apps.publications.models import LinkType
from coda.apps.users.models import User
from tests.fundingrequests import factory
from tests.fundingrequests.assertions import assert_correct_funding_request


@pytest.fixture(autouse=True)
@pytest.mark.django_db
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


@pytest.mark.django_db
def test__fundingrequest_wizard__first_step__when_valid_data__redirects_to_next_step(
    client: Client,
) -> None:
    form_data = factory.valid_author_dto(factory.institution().pk)
    response = client.post(reverse("fundingrequests:create_submitter"), form_data)

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
    form_data = factory.publication_dto(factory.journal().pk)
    response = client.post(reverse("fundingrequests:create_publication"), form_data)

    assertRedirects(response, reverse("fundingrequests:create_funding"))


@pytest.mark.django_db
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
) -> None:
    author = factory.valid_author_dto(factory.institution().pk)
    journal_pk = factory.journal().pk
    journal = {"journal": journal_pk}

    links = create_link_dtos()
    publication = factory.publication_dto(journal_pk, links=links)
    publication_post_data = create_publication_post_data(links, publication)
    funding = factory.funding_dto()

    client.post(reverse("fundingrequests:create_submitter"), author)
    client.post(reverse("fundingrequests:create_journal"), journal)
    client.post(reverse("fundingrequests:create_publication"), publication_post_data)
    response = client.post(reverse("fundingrequests:create_funding"), funding)

    funding_request = assert_correct_funding_request(author, publication, funding)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))


def create_link_dtos() -> list[LinkDto]:
    doi = LinkType.objects.create(name="DOI")
    url = LinkType.objects.create(name="URL")

    doi_link = LinkDto(link_type=int(doi.pk), link_value="10.1234/5678")
    url_link = LinkDto(link_type=int(url.pk), link_value="https://example.com")
    return [doi_link, url_link]


def create_publication_post_data(
    links: list[LinkDto], publication: PublicationDto
) -> dict[str, Any]:
    link_form_data: dict[str, list[str]] = {"link_type": [], "link_value": []}
    for link in links:
        link_form_data["link_type"].append(str(link["link_type"]))
        link_form_data["link_value"].append(str(link["link_value"]))

    publication_form_data = PublicationFormData(
        title=publication["title"],
        publication_state=publication["publication_state"],
        publication_date=publication["publication_date"],
    )

    return {**publication_form_data, **link_form_data}
