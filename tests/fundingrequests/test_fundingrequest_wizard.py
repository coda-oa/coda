from typing import Any, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto, parse_author
from coda.apps.authors.models import Author, PersonId
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import (
    CostDto,
    ExternalFundingDto,
    parse_external_funding,
    parse_payment,
)
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.institutions.models import Institution
from coda.apps.publications.dto import PublicationDto, parse_publication
from coda.apps.publications.forms import PublicationFormData
from coda.apps.users.models import User
from coda.fundingrequest import FundingOrganizationId, FundingRequest, FundingRequestId
from coda.publication import JournalId
from tests import domainfactory, dtofactory, modelfactory
from tests.authors.test__author import assert_author_eq
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.publications.test_publication_services import assert_publication_eq


@pytest.fixture(autouse=True)
@pytest.mark.django_db
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


def save_new_fundingrequest(journal_id: int | None = None) -> FundingRequestId:
    journal_id = journal_id or modelfactory.journal().pk
    funding_id = modelfactory.funding_organization().pk
    fr = domainfactory.fundingrequest(
        journal_id=JournalId(journal_id), funding_org_id=FundingOrganizationId(funding_id)
    )
    fr_id = fundingrequest_create(fr)
    return fr_id


@pytest.mark.django_db
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
) -> None:
    journal_id = modelfactory.journal().pk
    funder = modelfactory.funding_organization()

    author_dto = dtofactory.author_dto(modelfactory.institution().pk)
    journal_post_data = {"journal": journal_id}

    publication_dto = dtofactory.publication_dto(journal_id)
    publication_post_data = create_publication_post_data(publication_dto)
    external_funding = dtofactory.external_funding_dto(funder.pk)
    cost_dto = dtofactory.cost_dto()

    response = submit_wizard(
        client, author_dto, journal_post_data, publication_post_data, external_funding, cost_dto
    )

    expected = FundingRequest.new(
        parse_publication(publication_dto),
        parse_author(author_dto),
        parse_payment(cost_dto),
        parse_external_funding(external_funding),
    )
    actual = repository.first()
    assert actual is not None
    assert_fundingrequest_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
def test__updating_fundingrequest_submitter__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()
    affiliation = modelfactory.institution()

    new_author = dtofactory.author_dto(affiliation.pk)
    response = client.post(
        reverse("fundingrequests:update_submitter", kwargs={"pk": fr_id}),
        next() | new_author,
    )

    expected = parse_author(new_author)
    actual = repository.get_by_id(fr_id).submitter
    assert_author_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_publication__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    journal_id = modelfactory.journal().pk
    new_journal_id = modelfactory.journal().pk
    fr_id = save_new_fundingrequest(journal_id)

    publication_data = dtofactory.publication_dto(new_journal_id)
    publication_post_data = create_publication_post_data(publication_data)

    client.post(
        reverse("fundingrequests:update_publication", kwargs={"pk": fr_id}),
        next() | publication_post_data,
    )
    response = client.post(
        reverse("fundingrequests:update_publication", kwargs={"pk": fr_id}),
        next() | {"journal": new_journal_id},
    )

    expected = parse_publication(publication_data)
    actual = repository.get_by_id(fr_id).publication
    assert_publication_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_funding__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()

    new_funder = modelfactory.funding_organization()
    external_funding = dtofactory.external_funding_dto(new_funder.pk)
    cost_dto = dtofactory.cost_dto()

    response = client.post(
        reverse("fundingrequests:update_funding", kwargs={"pk": fr_id}),
        next() | external_funding | cost_dto,
    )

    fr = repository.get_by_id(fr_id)
    expected_payment = parse_payment(cost_dto)
    expected_funding = parse_external_funding(external_funding)
    assert fr.estimated_cost == expected_payment
    assert fr.external_funding == expected_funding
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_funding__without_external_funding__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()
    cost_dto = dtofactory.cost_dto()

    response = client.post(
        reverse("fundingrequests:update_funding", kwargs={"pk": fr_id}),
        next() | {"organization": "", "project_id": "", "project_name": ""} | cost_dto,
    )

    request = repository.get_by_id(fr_id)
    assert request.external_funding is None
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


def next() -> dict[str, str]:
    return {"action": "next"}


def submit_wizard(
    client: Client,
    author: AuthorDto,
    journal: dict[str, int],
    publication_post_data: dict[str, Any],
    external_funding: ExternalFundingDto,
    cost: CostDto,
) -> HttpResponse:
    client.post(reverse("fundingrequests:create_wizard"), next() | author)
    client.post(reverse("fundingrequests:create_wizard"), next() | journal)
    client.post(reverse("fundingrequests:create_wizard"), next() | publication_post_data)
    return cast(
        HttpResponse,
        client.post(reverse("fundingrequests:create_wizard"), next() | external_funding | cost),
    )


def create_publication_post_data(publication: PublicationDto) -> dict[str, Any]:
    link_form_data: dict[str, list[str]] = {"link_type": [], "link_value": []}
    for link in publication["links"]:
        link_form_data["link_type"].append(str(link["link_type"]))
        link_form_data["link_value"].append(str(link["link_value"]))

    publication_form_data = PublicationFormData(
        title=publication["title"],
        license=publication["license"],
        open_access_type=publication["open_access_type"],
        publication_state=publication["publication_state"],
        publication_date=(
            publication["publication_date"] if publication["publication_date"] else ""
        ),
    )

    # NOTE: authors are submitted as a single string from a textarea
    authors = ",".join(publication["authors"])
    return publication_form_data | link_form_data | {"authors": authors}


def author_dto_from_request(request: FundingRequest) -> AuthorDto:
    submitter = cast(Author, request.submitter)
    affiliation = cast(Institution, submitter.affiliation)
    identifier = cast(PersonId, submitter.identifier)
    return AuthorDto(
        name=submitter.name,
        email=str(submitter.email),
        affiliation=affiliation.pk,
        orcid=identifier.orcid,
        roles=[r.name for r in submitter.get_roles()],
    )
