from typing import Any

import pytest

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.services import fundingrequest_create, label_attach, label_create
from coda.color import Color
from tests.fundingrequests import factory


@pytest.mark.django_db
def test__searching_for_funding_requests_by_title__returns_matching_funding_requests() -> None:
    title = "The Search Term"
    matching_request = fundingrequest(title)

    _ = fundingrequest("No match")

    results = repository.search(title=title)

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_with_label__returns_matching_funding_requests() -> None:
    matching_request = fundingrequest("Match")
    first = label_create("The Label", Color())
    second = label_create("Another Label", Color())
    label_attach(matching_request.pk, first.pk)
    label_attach(matching_request.pk, second.pk)

    _ = fundingrequest("No match")

    results = repository.search(labels=[first.pk, second.pk])

    assert list(results) == [matching_request]


@pytest.mark.django_db
def test__searching_for_funding_requests_by_process_state__returns_matching_funding_requests() -> (
    None
):
    approved_request = fundingrequest()
    approved_request.approve()

    rejected_request = fundingrequest()
    rejected_request.reject()

    in_progress_request = fundingrequest()  # noqa: F841

    results = repository.search(processing_states=["approved", "rejected"])

    assert_contains_all(list(results), [approved_request, rejected_request])


def assert_contains_all(expected: list[Any], actual: list[Any]) -> None:
    assert len(expected) == len(actual)
    assert set(expected) == set(actual)


def fundingrequest(title: str = "") -> FundingRequest:
    journal = factory.journal()
    affiliation = factory.institution().pk
    author_dto = factory.valid_author_dto(affiliation)
    matching_publication = factory.publication_dto(journal.pk, title=title)
    matching_request = fundingrequest_create(
        author_dto, matching_publication, factory.funding_dto()
    )

    return matching_request
