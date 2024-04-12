from typing import Any

import pytest
from django.http import HttpRequest
from django.test import RequestFactory

from coda.apps.fundingrequests.wizardsteps import JournalStep
from coda.apps.journals.models import Journal
from tests import factory
from tests.test_wizard import DictStore


@pytest.fixture(autouse=True)
def store() -> DictStore:
    return DictStore()


@pytest.fixture
def journals() -> list[Journal]:
    return [factory.journal() for _ in range(3)]


@pytest.mark.django_db
def test__journal_step__journal_is_not_selected__is_invalid(
    store: DictStore, journals: list[Journal]
) -> None:
    first_journal = journals[0]
    sut = JournalStep()

    request = post({"journal_title": first_journal.title})

    assert sut.is_valid(request, store) is False


@pytest.mark.django_db
def test__journal_step__journal_is_selected__is_valid(
    store: DictStore, journals: list[Journal]
) -> None:
    first_journal = journals[0]
    sut = JournalStep()

    request = post({"journal": first_journal.pk})

    assert sut.is_valid(request, store) is True


@pytest.mark.django_db
def test__journal_step__journal_is_selected__done__store_selected_journal(
    store: DictStore, journals: list[Journal]
) -> None:
    first_journal = journals[0]
    sut = JournalStep()

    request = post({"journal": first_journal.pk})
    sut.done(request, store)

    assert store["journal"] == str(first_journal.pk)


@pytest.mark.django_db
def test__journal_step__journal_get_context_data__with_journal_title__finds_journals(
    store: DictStore, journals: list[Journal]
) -> None:
    first_journal = journals[0]
    sut = JournalStep()

    request = post({"journal_title": first_journal.title})
    ctx = sut.get_context_data(request, store)

    assert list(ctx["journals"]) == [first_journal]
    assert ctx["journal_title"] == first_journal.title


@pytest.mark.django_db
def test__journal_step__journal_in_store__get_context_data__finds_selected_journal(
    store: DictStore, journals: list[Journal]
) -> None:
    first_journal = journals[0]
    store["journal"] = first_journal.pk

    sut = JournalStep()

    request = post()
    ctx = sut.get_context_data(request, store)

    assert ctx["selected_journal"] == first_journal
    assert ctx["journal_title"] == first_journal.title
    assert list(ctx["journals"]) == [first_journal]


@pytest.mark.django_db
def test__journal_step__journal_data_in_post_and_store__get_context_data__prefers_post_data(
    store: DictStore, journals: list[Journal]
) -> None:
    first_journal = journals[0]
    second_journal = journals[1]
    store["selected_journal"] = first_journal.pk

    sut = JournalStep()

    request = post({"journal_title": second_journal.title})
    ctx = sut.get_context_data(request, store)

    assert list(ctx["journals"]) == [second_journal]
    assert ctx["journal_title"] == second_journal.title


_request_factory = RequestFactory()


def post(data: dict[str, Any] | None = None) -> HttpRequest:
    return _request_factory.post("/", data)
