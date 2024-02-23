from typing import cast

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Person
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from tests import test_orcid
from tests.fundingrequests.test_fundingrequest_id import journal


def institution() -> Institution:
    return Institution.objects.create(name="Test Institution")


def valid_author_dto(affiliation_pk: int) -> AuthorDto:
    return AuthorDto(
        name="Josiah Carberry",
        email="carberry@example.com",
        orcid=test_orcid.JOSIAH_CARBERRY,
        affiliation=affiliation_pk,
    )


def publication_dto(journal: Journal) -> PublicationDto:
    return PublicationDto(
        title="My Paper",
        journal=journal.pk,
        publication_state="submitted",
        publication_date="2021-01-01",
    )


def funding_dto() -> FundingDto:
    return FundingDto(estimated_cost=100, estimated_cost_currency="USD")


@pytest.mark.django_db
def test__fundingrequest_wizard__first_step__when_valid_data__stores_data_in_session_and_redirects_to_next_step(
    client: Client,
) -> None:
    affiliation = institution()

    form_data = valid_author_dto(affiliation.pk)
    response = client.post(reverse("fundingrequests:create"), form_data)

    assert client.session["submitter"] == form_data
    assertRedirects(response, reverse("fundingrequests:create_publication"))


@pytest.mark.django_db
def test__fundingrequest_wizard_publication_step__when_valid_data__stores_data_in_session_and_redirects_to_next_step(
    client: Client,
) -> None:
    _journal = journal()
    form_data = publication_dto(_journal)
    response = client.post(reverse("fundingrequests:create_publication"), form_data)

    assert client.session["publication"] == form_data
    assertRedirects(response, reverse("fundingrequests:create_funding"))


@pytest.mark.django_db
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
) -> None:
    author = valid_author_dto(institution().pk)
    publication = publication_dto(journal())
    session = client.session
    session["submitter"] = author
    session["publication"] = publication
    session.save()

    funding = funding_dto()
    response = client.post(reverse("fundingrequests:create_funding"), funding)

    funding_request = assert_correct_funding_request(author, publication, funding)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))


def assert_correct_funding_request(
    author: AuthorDto,
    publication: PublicationDto,
    funding: FundingDto,
) -> FundingRequest:
    funding_request = FundingRequest.objects.first()
    assert funding_request is not None

    assert_author_equal(author, funding_request)
    assert_publication_equal(publication, funding_request)
    assert_funding_details_equal(funding, funding_request)
    assert funding_request.processing_status == "in_progress"
    return funding_request


def assert_funding_details_equal(funding: FundingDto, funding_request: FundingRequest) -> None:
    assert funding_request.estimated_cost == funding["estimated_cost"]
    assert funding_request.estimated_cost_currency == funding["estimated_cost_currency"]


def assert_publication_equal(publication: PublicationDto, funding_request: FundingRequest) -> None:
    assert funding_request.publication.title == publication["title"]
    assert funding_request.publication.journal.pk == publication["journal"]


def assert_author_equal(author: AuthorDto, funding_request: FundingRequest) -> None:
    assert funding_request.submitter is not None

    details = cast(Person, funding_request.submitter.details)
    assert details.name == author["name"]
    assert details.email == author["email"]
    assert details.orcid == author["orcid"]
