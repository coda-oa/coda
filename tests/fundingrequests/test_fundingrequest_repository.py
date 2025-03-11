from datetime import date
from typing import Any, cast

import pytest

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services.labels import label_attach
from coda.apps.fundingrequests.services.labels import label_create
from coda.apps.journals.models import Journal
from coda.color import Color
from coda.date import DateRange
from coda.fundingrequest import FundingRequestId, Review
from coda.fundingrequest import FundingOrganizationId, NoContact
from coda.fundingrequest.review import ReviewResult
from coda.money import Currency, Money
from coda.publication import Authors, JournalId
from coda.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq


@pytest.mark.django_db
def test__saving_fungingrequest__get_by_id__returns_fundingrequest() -> None:
    journal = JournalId(modelfactory.journal().id)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    id = repository.save(request)

    result = repository.get_by_id(id)

    assert_fundingrequest_eq(result, request)


@pytest.mark.django_db
def test__existing_fundingrequest__save__updates_fundingrequest() -> None:
    journal = JournalId(modelfactory.journal().id)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    id = repository.save(request)

    new_funding = FundingOrganizationId(modelfactory.funding_organization().pk)
    expected = domainfactory.fundingrequest(
        id=id,
        request_id=request.request_id,
        journal_id=journal,
        funding_org_id=new_funding,
    )
    repository.save(expected)

    actual = repository.get_by_id(id)
    assert_fundingrequest_eq(actual, expected)


@pytest.mark.django_db
def test__fundingrequest_without_extra_contact__save__get_by_id_returns_fundingrequest_without_contact() -> (
    None
):
    journal = JournalId(modelfactory.journal().id)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    request.extra_contact = NoContact
    id = repository.save(request)

    result = repository.get_by_id(id)

    assert result.extra_contact == NoContact


@pytest.mark.django_db
def test__searching_for_funding_requests_by_title__returns_matching_funding_requests() -> None:
    title = "The Search Term"
    matching_request = modelfactory.fundingrequest(title)

    _ = modelfactory.fundingrequest("No match")

    results = repository.search(title=title)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_author__returns_matching_funding_requests() -> None:
    matching_author = domainfactory.author()
    matching_request = modelfactory.fundingrequest(authors=Authors([matching_author]))

    non_matching_author = domainfactory.author()
    non_matching_author.name = NonEmptyStr("Not the submitter")
    _ = modelfactory.fundingrequest("No match", authors=Authors([non_matching_author]))

    results = repository.search(author=matching_author.name)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_with_label__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest("Match")
    first = label_create("The Label", Color())
    second = label_create("Another Label", Color())
    label_attach(matching_request, first)
    label_attach(matching_request, second)

    _ = modelfactory.fundingrequest("No match")

    results = repository.search(labels=[first.pk, second.pk])

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_process_state__returns_matching_funding_requests() -> (
    None
):
    approved_request = modelfactory.fundingrequest()
    approved_request_id = FundingRequestId(approved_request.id)
    repository.save_review(Review(approved_request_id).approved(Money(100, Currency.EUR)))

    rejected_request = modelfactory.fundingrequest()
    rejected_request_id = FundingRequestId(rejected_request.id)
    repository.save_review(Review(rejected_request_id).rejected())

    in_progress_request = modelfactory.fundingrequest()  # noqa: F841

    results = repository.search(processing_states=[ReviewResult.Approved, ReviewResult.Rejected])

    assert_contains_all(list(results), [approved_request, rejected_request])


@pytest.mark.django_db
def test__searching_for_funding_requests_by_publisher__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    journal = cast(Journal, matching_request.publication.article_journal)
    matching_publisher = journal.publisher

    _ = modelfactory.fundingrequest("No match")

    results = repository.search(publisher=matching_publisher.name)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_with_start_and_end_date__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.created_at = date(2021, 3, 1)
    matching_request.save()

    no_match = modelfactory.fundingrequest("No match")
    no_match.created_at = date(2021, 6, 1)
    no_match.save()

    start_date = date(2021, 1, 1)
    end_date = date(2021, 5, 1)
    date_range = DateRange(start_date, end_date)

    results = repository.search(date_range=date_range)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_with_no_start_date__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.created_at = date(2021, 3, 1)
    matching_request.save()

    no_match = modelfactory.fundingrequest("No match")
    no_match.created_at = date(2021, 6, 1)
    no_match.save()

    date_range = DateRange.create(end=date(2021, 5, 1))

    results = repository.search(date_range=date_range)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_with_no_end_date__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.created_at = date(2021, 3, 1)
    matching_request.save()

    no_match = modelfactory.fundingrequest("No match")
    no_match.created_at = date(2020, 12, 31)
    no_match.save()

    date_range = DateRange.create(start=date(2021, 1, 1))

    results = repository.search(date_range=date_range)

    assert list(results) == [matching_request]


def assert_contains_all(expected: list[Any], actual: list[Any]) -> None:
    assert len(expected) == len(actual)
    assert set(expected) == set(actual)
