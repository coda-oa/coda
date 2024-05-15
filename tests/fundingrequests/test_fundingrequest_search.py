from typing import Any, cast

import pytest
from django.template import RequestContext
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.services import label_attach, label_create
from coda.color import Color
from coda.fundingrequest import Review
from tests import dtofactory, modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests__shows_all_funding_requests(client: Client) -> None:
    requests = {modelfactory.fundingrequest(), modelfactory.fundingrequest()}

    response = search_fundingrequests(client)

    assert_contains(response.context, requests)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_title__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    title = "The Search Term"
    matching_request = modelfactory.fundingrequest(title)

    _ = modelfactory.fundingrequest("No match")

    response = search_fundingrequests(client, by_title(title))

    assert_contains(response.context, {matching_request})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_funding_request_by_submitter__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    matching_request = modelfactory.fundingrequest()
    submitter = cast(Author, matching_request.submitter)

    non_matching_submitter = dtofactory.author_dto()
    non_matching_submitter["name"] = "Not the submitter"
    _ = modelfactory.fundingrequest("No match", non_matching_submitter)

    response = search_fundingrequests(client, by_submitter(submitter.name))

    assert_contains(response.context, {matching_request})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_with_invalid_search_type__shows_all_funding_requests(client: Client) -> None:
    requests = {modelfactory.fundingrequest(), modelfactory.fundingrequest()}

    response = search_fundingrequests(client, {"search_type": "invalid"})

    assert_contains(response.context, requests)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_label__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    matching_request = modelfactory.fundingrequest()
    first = label_create("The Label", Color())
    label_attach(matching_request, first)
    second = label_create("Another Label", Color())
    label_attach(matching_request, second)

    _ = modelfactory.fundingrequest("No match")

    response = search_fundingrequests(client, {"labels": [first.pk, second.pk]})

    assert_contains(response.context, {matching_request})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_process_state__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    approved_request = modelfactory.fundingrequest()
    approved_request.approve()

    rejected_request = modelfactory.fundingrequest()
    rejected_request.reject()

    in_progress_request = modelfactory.fundingrequest()  # noqa: F841

    query = {"processing_status": [Review.Approved.value, Review.Rejected.value]}
    response = search_fundingrequests(client, query)

    assert_contains(response.context, {approved_request, rejected_request})


def search_fundingrequests(client: Client, query: dict[str, Any] | None = None) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))


def by_title(title: str) -> dict[str, str]:
    return {"search_type": "title", "search_term": title}


def by_submitter(submitter: str) -> dict[str, str]:
    return {"search_type": "submitter", "search_term": submitter}


def assert_contains(context: RequestContext, requests: set[FundingRequest]) -> None:
    ids = [viewmodel.id for viewmodel in context["funding_requests"]]
    assert len(ids) == len(requests)
    assert all(request.id in ids for request in requests)
