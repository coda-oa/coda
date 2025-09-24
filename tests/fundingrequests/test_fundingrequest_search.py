import datetime
from typing import Any, cast

import pytest
from django.template import RequestContext
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.fundingrequest import AnyFundingRequest, FundingRequestId, Review
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors
from coda.domain.publication.publication import JournalId
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory


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
def test__searching_funding_request_by_author__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    matching_author = domainfactory.author()
    matching_request = modelfactory.fundingrequest(authors=Authors([matching_author]))

    non_matching_author = domainfactory.author()
    non_matching_author.name = NonEmptyStr("Not the submitter")
    _ = modelfactory.fundingrequest("No match", authors=Authors([non_matching_author]))

    response = search_fundingrequests(client, by_submitter(matching_author.name))

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
    approved_request_id = FundingRequestId(approved_request.id)
    repository.save_review(Review(approved_request_id).update_review(ReviewResult.Approved, Money(100, Currency.EUR)))

    rejected_request = modelfactory.fundingrequest()
    rejected_request_id = FundingRequestId(rejected_request.id)
    repository.save_review(Review(rejected_request_id).update_review(ReviewResult.Rejected))

    in_progress_request = modelfactory.fundingrequest()  # noqa: F841

    query = {"processing_status": [ReviewResult.Approved.value, ReviewResult.Rejected.value]}
    response = search_fundingrequests(client, query)

    assert_contains(response.context, {approved_request, rejected_request})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_date__shows_matching_funding_requests(
    client: Client,
) -> None:
    journal_id = JournalId(modelfactory.journal().id)
    funding_org_id = FundingOrganizationId(modelfactory.funding_organization().id)
    request_date = datetime.date(2023, 10, 1)
    request_id = PublicFundingRequestId.create(request_date)

    matching_request = domainfactory.fundingrequest(
        journal_id=journal_id,
        request_id=request_id,
        funding_org_id=funding_org_id,
    )
    matching_request.id = repository.create(matching_request)

    query = {"start_date": request_date.isoformat(), "end_date": request_date.isoformat()}
    response = search_fundingrequests(client, query)

    requests: set[AnyFundingRequest] = {matching_request}
    assert_contains(response.context, requests)


def search_fundingrequests(client: Client, query: dict[str, Any] | None = None) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))


def by_title(title: str) -> dict[str, str]:
    return {"search_type": "title", "search_term": title}


def by_submitter(submitter: str) -> dict[str, str]:
    return {"search_type": "author", "search_term": submitter}


def assert_contains(
    context: RequestContext, requests: set[FundingRequestModel] | set[AnyFundingRequest]
) -> None:
    ids = [viewmodel.id for viewmodel in context["entities"]]
    assert len(ids) == len(requests)
    assert all(request.id in ids for request in requests)
