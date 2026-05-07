import datetime
from typing import Any, cast

import pytest
from django.template import RequestContext
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.contract import ContractYear
from coda.domain.date import DateRange
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors, JournalId
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests__shows_all_funding_requests(client: Client) -> None:
    requests = {modelfactory.fundingrequest().pk, modelfactory.fundingrequest().pk}

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

    assert_contains(response.context, {matching_request.pk})


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

    assert_contains(response.context, {matching_request.pk})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_with_invalid_search_type__shows_all_funding_requests(client: Client) -> None:
    requests = {modelfactory.fundingrequest().pk, modelfactory.fundingrequest().pk}

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

    assert_contains(response.context, {matching_request.pk})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_process_state__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    approved_request = modelfactory.fundingrequest()
    approved_request_id = FundingRequestId(approved_request.pk)
    repository.save_review(
        approved_request_id, Review().update_review(ReviewResult.Approved, Money(100, Currency.EUR))
    )

    rejected_request = modelfactory.fundingrequest()
    rejected_request_id = FundingRequestId(rejected_request.pk)
    repository.save_review(rejected_request_id, Review().update_review(ReviewResult.Rejected))

    in_progress_request = modelfactory.fundingrequest()  # noqa: F841

    query = {"processing_status": [ReviewResult.Approved.value, ReviewResult.Rejected.value]}
    response = search_fundingrequests(client, query)

    assert_contains(response.context, {approved_request.pk, rejected_request.pk})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_date__shows_matching_funding_requests(
    client: Client,
) -> None:
    journal_id = JournalId(modelfactory.journal().pk)
    funding_org_id = FundingOrganizationId(modelfactory.funding_organization().pk)
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

    requests: set[int] = {matching_request.id.pk}
    assert_contains(response.context, requests)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_payment_method__shows_matching_funding_requests(
    client: Client,
) -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.payment_method = "direct"
    matching_request.save()

    non_matching_request = modelfactory.fundingrequest()
    non_matching_request.payment_method = "reimbursement"
    non_matching_request.save()

    query = {"payment_methods": ["direct"]}
    response = search_fundingrequests(client, query)

    assert_contains(response.context, {matching_request.pk})


def search_fundingrequests(client: Client, query: dict[str, Any] | None = None) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))


def by_title(title: str) -> dict[str, str]:
    return {"search_type": "title", "search_term": title}


def by_submitter(submitter: str) -> dict[str, str]:
    return {"search_type": "author", "search_term": submitter}


def assert_contains(context: RequestContext, requests: set[int]) -> None:
    ids = [viewmodel.id for viewmodel in context["entities"]]
    assert len(ids) == len(requests)
    assert all(request in ids for request in requests)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_invalid_contract_years__shows_only_matching(
    client: Client,
) -> None:
    """Filter shows only requests with contract years outside contract period."""
    journal_id = JournalId(modelfactory.journal().pk)
    funding_org_id = FundingOrganizationId(modelfactory.funding_organization().pk)
    contract = domainfactory.contract(
        period=DateRange.create(start=datetime.date(2023, 1, 1), end=datetime.date(2025, 12, 31))
    )
    contract.id = contract_repository.create(contract)

    invalid_contract_year = ContractYear(year=2026, contract=contract)
    pub_with_invalid = domainfactory.publication(journal_id, contracts=(invalid_contract_year,))

    request_with_invalid = domainfactory.fundingrequest(funding_org_id=funding_org_id)
    request_with_invalid.publication = pub_with_invalid
    request_with_invalid.id = repository.create(request_with_invalid)

    valid_contract_year = contract.in_year(2024)
    pub_with_valid = domainfactory.publication(journal_id, contracts=(valid_contract_year,))

    request_with_valid = domainfactory.fundingrequest(funding_org_id=funding_org_id)
    request_with_valid.publication = pub_with_valid
    request_with_valid.id = repository.create(request_with_valid)

    request_without_contract = domainfactory.fundingrequest(
        journal_id=journal_id, funding_org_id=funding_org_id
    )
    request_without_contract.id = repository.create(request_without_contract)

    query = {"invalid_contract_years": "on"}
    response = search_fundingrequests(client, query)

    expected = {request_with_invalid.id.pk}
    assert_contains(response.context, expected)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_publications_publication_state__shows_matching_funding_requests(
    client: Client,
) -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.publication.publication_state = "Published"
    matching_request.publication.online_publication_date = datetime.date(2023, 1, 1)
    matching_request.publication.save()

    non_matching_request = modelfactory.fundingrequest()
    non_matching_request.publication.publication_state = "Rejected"
    non_matching_request.publication.save()

    query = {"publication_states": ["Published"]}
    response = search_fundingrequests(client, query)

    assert_contains(response.context, {matching_request.pk})
