from datetime import date
from typing import Any, cast

import pytest

from coda.apps.fundingrequests import fundingrequest_query, repository
from coda.apps.fundingrequests.mappers import FundingRequestDomainMapper
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import publication_repository
from coda.contexts.fundingrequest.dto.commands import CreateFundingRequestDto
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.date import DateRange
from coda.domain.fundingrequest import (
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    NoContact,
    Review,
)
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors, Doi, JournalId
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq


@pytest.mark.django_db
def test__saving_fungingrequest__get_by_id__returns_fundingrequest() -> None:
    journal = JournalId(modelfactory.journal().pk)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    id = repository.create(request)

    result = repository.get_by_id(id)

    assert_fundingrequest_eq(result, request)


@pytest.mark.django_db
def test__existing_fundingrequest__create_again__raises_error() -> None:
    journal = JournalId(modelfactory.journal().pk)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    request.id = repository.create(request)

    with pytest.raises(repository.FundingRequestAlreadyExists):
        repository.create(request)


@pytest.mark.django_db
def test__existing_fundingrequest__update__updates_fundingrequest() -> None:
    journal = JournalId(modelfactory.journal().pk)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    id = repository.create(
        domainfactory.fundingrequest(
            journal_id=journal,
            funding_org_id=funding_org,
        )
    )
    request = repository.get_article_request(id)

    new_funding = FundingOrganizationId(modelfactory.funding_organization().pk)
    expected = FundingRequest(
        id=id,
        request_id=request.request_id,
        publication=domainfactory.publication(journal, id=request.publication.id),
        estimated_cost=domainfactory.payment(),
        extra_contact=domainfactory.fundingrequest_contact(),
        external_funding=[domainfactory.external_funding(new_funding)],
    )
    repository.update(expected)

    actual = repository.get_by_id(id)
    assert_fundingrequest_eq(actual, expected)
    assert len(repository.all()) == 1
    assert len(publication_repository.all()) == 1


@pytest.mark.django_db
def test__unsaved_fundingrequest__update__raises_error() -> None:
    journal = JournalId(modelfactory.journal().id)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)

    with pytest.raises(repository.UnsavedFundingRequest):
        repository.update(request)


@pytest.mark.django_db
def test__fundingrequest_without_extra_contact__save__get_by_id_returns_fundingrequest_without_contact() -> (
    None
):
    journal = JournalId(modelfactory.journal().id)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    request.extra_contact = NoContact
    id = repository.create(request)

    result = repository.get_by_id(id)

    assert result.extra_contact == NoContact


@pytest.mark.django_db
def test__searching_for_funding_requests_by_title__returns_matching_funding_requests() -> None:
    title = "The Search Term"
    matching_request = modelfactory.fundingrequest(title)

    _ = modelfactory.fundingrequest("No match")

    results = fundingrequest_query.search(fundingrequest_query.GenericSearchCriteria(title))

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_author__returns_matching_funding_requests() -> None:
    matching_author = domainfactory.author()
    matching_request = modelfactory.fundingrequest(authors=Authors([matching_author]))

    non_matching_author = domainfactory.author()
    non_matching_author.name = NonEmptyStr("Not the submitter")
    _ = modelfactory.fundingrequest("No match", authors=Authors([non_matching_author]))

    results = fundingrequest_query.search(
        fundingrequest_query.GenericSearchCriteria(matching_author.name)
    )

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_with_label__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest("Match")
    first = label_create("The Label", Color())
    second = label_create("Another Label", Color())
    label_attach(matching_request, first)
    label_attach(matching_request, second)

    _ = modelfactory.fundingrequest("No match")

    results = fundingrequest_query.search(
        fundingrequest_query.LabelsSearchCriteria([first.pk, second.pk])
    )

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_process_state__returns_matching_funding_requests() -> (
    None
):
    approved_request = modelfactory.fundingrequest()
    approved_request_id = FundingRequestId(approved_request.id)
    repository.save_review(
        Review(approved_request_id).update_review(ReviewResult.Approved, Money(100, Currency.EUR))
    )

    rejected_request = modelfactory.fundingrequest()
    rejected_request_id = FundingRequestId(rejected_request.id)
    repository.save_review(Review(rejected_request_id).update_review(ReviewResult.Rejected))

    in_progress_request = modelfactory.fundingrequest()  # noqa: F841

    results = fundingrequest_query.search(
        fundingrequest_query.ReviewResultCriteria([ReviewResult.Approved, ReviewResult.Rejected])
    )

    assert_contains_all(list(results), [approved_request, rejected_request])


@pytest.mark.django_db
def test__searching_for_funding_requests_by_publisher__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    journal = cast(Journal, matching_request.publication.article_journal)
    matching_publisher = journal.publisher

    _ = modelfactory.fundingrequest("No match")

    results = fundingrequest_query.search(
        fundingrequest_query.GenericSearchCriteria(matching_publisher.name)
    )

    assert list(results) == [matching_request]


@pytest.mark.django_db
@pytest.mark.parametrize("doi_string", [Doi("10.0000/1234").value(), Doi("10.0000/1234").url()])
def test__searching_for_doi__returns_matching_funding_requests(doi_string: str) -> None:
    journal = JournalId(modelfactory.journal().pk)
    funder = FundingOrganizationId(modelfactory.funding_organization().pk)
    matching_request = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funder)
    matching_request.publication.links = {Doi(doi_string)}
    matching_request.id = fundingrequests.create_fundingrequest(
        CreateFundingRequestDto.from_fundingrequest(matching_request)
    )

    results = fundingrequest_query.search(fundingrequest_query.GenericSearchCriteria(doi_string))

    assert_fundingrequest_eq(FundingRequestDomainMapper.map(results.get()), matching_request)


@pytest.mark.django_db
def test__searching_for_eissn__returns_matching_fundingrequest_in_journal() -> None:
    funder = FundingOrganizationId(modelfactory.funding_organization().pk)
    matching_journal = modelfactory.journal()
    match = domainfactory.fundingrequest(
        journal_id=JournalId(matching_journal.pk),
        funding_org_id=funder,
    )
    match.id = fundingrequests.create_fundingrequest(
        CreateFundingRequestDto.from_fundingrequest(match)
    )

    non_matching_journal = modelfactory.journal()
    no_match = domainfactory.fundingrequest(
        journal_id=JournalId(non_matching_journal.pk),
        funding_org_id=funder,
    )
    no_match.id = fundingrequests.create_fundingrequest(
        CreateFundingRequestDto.from_fundingrequest(no_match)
    )

    results = fundingrequest_query.search(
        fundingrequest_query.GenericSearchCriteria(matching_journal.eissn)
    )

    assert len(results) == 1
    assert_fundingrequest_eq(FundingRequestDomainMapper.map(results.get()), match)


@pytest.mark.django_db
def test__searching_with_start_and_end_date__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.request_date = date(2021, 3, 1)
    matching_request.save()

    no_match = modelfactory.fundingrequest("No match")
    no_match.request_date = date(2021, 6, 1)
    no_match.save()

    start_date = date(2021, 1, 1)
    end_date = date(2021, 5, 1)

    results = fundingrequest_query.search(
        fundingrequest_query.DateRangeCriteria(DateRange.create(start=start_date, end=end_date))
    )

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_with_no_start_date__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.request_date = date(2021, 3, 1)
    matching_request.save()

    no_match = modelfactory.fundingrequest("No match")
    no_match.request_date = date(2021, 6, 1)
    no_match.save()

    end_date = date(2021, 5, 1)

    results = fundingrequest_query.search(
        fundingrequest_query.DateRangeCriteria(DateRange.create(end=end_date))
    )

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_with_no_end_date__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_request.request_date = date(2021, 3, 1)
    matching_request.save()

    no_match = modelfactory.fundingrequest("No match")
    no_match.request_date = date(2020, 12, 31)
    no_match.save()

    start_date = date(2021, 1, 1)

    results = fundingrequest_query.search(
        fundingrequest_query.DateRangeCriteria(DateRange.create(start=start_date))
    )

    assert list(results) == [matching_request]


def assert_contains_all(expected: list[Any], actual: list[Any]) -> None:
    assert len(expected) == len(actual)
    assert set(expected) == set(actual)
