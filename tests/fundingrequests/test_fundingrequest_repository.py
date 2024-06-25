from datetime import date
from typing import Any, cast

import pytest

from coda.apps.authors.models import Author
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services import label_attach, label_create
from coda.color import Color
from coda.fundingrequest import Review
from tests import dtofactory, modelfactory


@pytest.mark.django_db
def test__searching_for_funding_requests_by_title__returns_matching_funding_requests() -> None:
    title = "The Search Term"
    matching_request = modelfactory.fundingrequest(title)

    _ = modelfactory.fundingrequest("No match")

    results = repository.search(title=title)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_submitter__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    submitter = cast(Author, matching_request.submitter)

    non_matching_submitter = dtofactory.author_dto()
    non_matching_submitter["name"] = "Not the submitter"
    _ = modelfactory.fundingrequest("No match", non_matching_submitter)

    results = repository.search(submitter=submitter.name)

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
    approved_request.approve()

    rejected_request = modelfactory.fundingrequest()
    rejected_request.reject()

    in_progress_request = modelfactory.fundingrequest()  # noqa: F841

    results = repository.search(processing_states=[Review.Approved.value, Review.Rejected.value])

    assert_contains_all(list(results), [approved_request, rejected_request])


@pytest.mark.django_db
def test__searching_for_funding_requests_by_publisher__returns_matching_funding_requests() -> None:
    matching_request = modelfactory.fundingrequest()
    matching_publisher = matching_request.publication.journal.publisher

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
    date_range = repository.DateRange(start_date, end_date)

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

    date_range = repository.DateRange.create(end=date(2021, 5, 1))

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

    date_range = repository.DateRange.create(start=date(2021, 1, 1))

    results = repository.search(date_range=date_range)

    assert list(results) == [matching_request]


def assert_contains_all(expected: list[Any], actual: list[Any]) -> None:
    assert len(expected) == len(actual)
    assert set(expected) == set(actual)
