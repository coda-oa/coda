import json
from typing import Any, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto, parse_author
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import (
    CostDto,
    ExternalFundingDto,
    parse_external_funding,
    parse_payment,
)
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import PublicationDto, PublicationMetaDto, parse_publication
from coda.apps.users.models import User
from coda.fundingrequest import FundingOrganizationId, FundingRequest, FundingRequestId
from coda.publication import JournalId, VocabularyConcept
from tests import domainfactory, dtofactory, modelfactory
from tests.authors.test__author import assert_author_eq
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.publications.test_publication_services import as_domain_concept, assert_publication_eq


@pytest.fixture(autouse=True)
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


@pytest.fixture(autouse=True)
def prepare_global_settings() -> None:
    GlobalPreferences.set_subject_classification_vocabulary(modelfactory.vocabulary())
    GlobalPreferences.set_publication_type_vocabulary(modelfactory.vocabulary())


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
    publication_dto = dtofactory.publication_dto(
        journal_id, publication_type=publication_type(), subject_area=subject_area()
    )
    external_funding = dtofactory.external_funding_dto(funder.pk)
    cost_dto = dtofactory.cost_dto()

    response = submit_wizard(client, author_dto, publication_dto, external_funding, cost_dto)

    expected = FundingRequest.new(
        parse_publication(publication_dto),
        parse_author(author_dto),
        parse_payment(cost_dto),
        [parse_external_funding(external_funding)],
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

    publication_dto = dtofactory.publication_dto(
        new_journal_id, publication_type=publication_type(), subject_area=subject_area()
    )
    journal_post_data = {"journal": new_journal_id}

    client.post(
        reverse("fundingrequests:update_publication", kwargs={"pk": fr_id}),
        next() | as_form_data(publication_dto),
    )
    response = client.post(
        reverse("fundingrequests:update_publication", kwargs={"pk": fr_id}),
        next() | journal_post_data,
    )

    expected = parse_publication(publication_dto)
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
    expected_funding = [parse_external_funding(external_funding)]
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
    assert request.external_funding == []
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


def next() -> dict[str, str]:
    return {"action": "next"}


def submit_wizard(
    client: Client,
    author: AuthorDto,
    publication: PublicationDto,
    external_funding: ExternalFundingDto,
    cost: CostDto,
) -> HttpResponse:
    client.post(reverse("fundingrequests:create_wizard"), next() | author)
    client.post(
        reverse("fundingrequests:create_wizard"),
        next() | {"journal": publication["journal"]["journal_id"]},
    )
    client.post(reverse("fundingrequests:create_wizard"), next() | as_form_data(publication))
    return cast(
        HttpResponse,
        client.post(reverse("fundingrequests:create_wizard"), next() | external_funding | cost),
    )


def subject_area() -> VocabularyConcept:
    concept_model = GlobalPreferences.get_subject_classification_vocabulary().concepts.first()
    assert concept_model is not None
    return as_domain_concept(concept_model)


def publication_type() -> VocabularyConcept:
    concept_model = GlobalPreferences.get_publication_type_vocabulary().concepts.first()
    assert concept_model is not None
    return as_domain_concept(concept_model)


def as_form_data(publication: PublicationDto) -> dict[str, Any]:
    meta = publication["meta"]
    meta["online_publication_date"] = meta["online_publication_date"] or ""
    meta["print_publication_date"] = meta["print_publication_date"] or ""

    # NOTE: authors are submitted as a single string from a textarea
    authors = ",".join(publication["authors"])

    concepts = _concepts_to_json(meta)

    meta_reduced = dict(meta)
    meta_reduced.pop("subject_area")
    meta_reduced.pop("publication_type")
    meta_reduced.pop("subject_area_vocabulary")
    meta_reduced.pop("publication_type_vocabulary")

    link_form_data: dict[str, list[str]] = {"link_type": [], "link_value": []}
    for link in publication["links"]:
        link_form_data["link_type"].append(str(link["link_type"]))
        link_form_data["link_value"].append(str(link["link_value"]))

    return meta_reduced | {"authors": authors} | concepts | link_form_data


def _concepts_to_json(meta: PublicationMetaDto) -> dict[str, str]:
    return {
        "subject_area": json.dumps(
            {
                "concept": meta["subject_area"],
                "vocabulary": meta["subject_area_vocabulary"],
            }
        ),
        "publication_type": json.dumps(
            {
                "concept": meta["publication_type"],
                "vocabulary": meta["publication_type_vocabulary"],
            }
        ),
    }
