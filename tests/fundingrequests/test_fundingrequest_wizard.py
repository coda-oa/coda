import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.models import LinkType

from tests.fundingrequests import factory
from tests.fundingrequests.assertions import assert_correct_funding_request


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
    doi = LinkType.objects.create(name="DOI")
    url = LinkType.objects.create(name="URL")

    doi_link = LinkDto(link_type_id=int(doi.pk), value="10.1234/5678")
    url_link = LinkDto(link_type_id=int(url.pk), value="https://example.com")
    publication = factory.publication_dto(links=[doi_link, url_link])
    link_form_data = {
        "linktype": [doi_link["link_type_id"], url_link["link_type_id"]],
        "linkvalue": [doi_link["value"], url_link["value"]],
    }

    publication_data = {**publication, **link_form_data}
    print(publication_data)

    funding = factory.funding_dto()

    client.post(reverse("fundingrequests:create_submitter"), author)
    client.post(reverse("fundingrequests:create_journal"), journal)
    client.post(reverse("fundingrequests:create_publication"), publication_data)
    response = client.post(reverse("fundingrequests:create_funding"), funding)

    funding_request = assert_correct_funding_request(author, publication, journal_pk, funding)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))
