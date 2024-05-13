from typing import Any, cast

import pytest

from coda.apps.authors.models import Author
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services import label_attach, label_create
from coda.color import Color
from coda.fundingrequest import Review
from tests import factory


@pytest.mark.django_db
def test__searching_for_funding_requests_by_title__returns_matching_funding_requests() -> None:
    title = "The Search Term"
    matching_request = factory.fundingrequest(title)

    _ = factory.fundingrequest("No match")

    results = repository.search(title=title)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_submitter__returns_matching_funding_requests() -> None:
    matching_request = factory.fundingrequest()
    submitter = cast(Author, matching_request.submitter)

    non_matching_submitter = factory.author_dto()
    non_matching_submitter["name"] = "Not the submitter"
    _ = factory.fundingrequest("No match", non_matching_submitter)

    results = repository.search(submitter=submitter.name)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_with_label__returns_matching_funding_requests() -> None:
    matching_request = factory.fundingrequest("Match")
    first = label_create("The Label", Color())
    second = label_create("Another Label", Color())
    label_attach(matching_request, first)
    label_attach(matching_request, second)

    _ = factory.fundingrequest("No match")

    results = repository.search(labels=[first.pk, second.pk])

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_process_state__returns_matching_funding_requests() -> (
    None
):
    approved_request = factory.fundingrequest()
    approved_request.approve()

    rejected_request = factory.fundingrequest()
    rejected_request.reject()

    in_progress_request = factory.fundingrequest()  # noqa: F841

    results = repository.search(processing_states=[Review.Approved.value, Review.Rejected.value])

    assert_contains_all(list(results), [approved_request, rejected_request])


def assert_contains_all(expected: list[Any], actual: list[Any]) -> None:
    assert len(expected) == len(actual)
    assert set(expected) == set(actual)
