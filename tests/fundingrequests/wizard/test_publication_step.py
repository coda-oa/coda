import json
from django.http import HttpRequest
from django.test import RequestFactory
import pytest

from coda.apps.fundingrequests.views.wizard.wizardsteps import PublicationStep
from tests.test_wizard import DictStore

request_factory = RequestFactory()

publication_type = {"concept": "2", "vocabulary": "4"}
subject_area = {"concept": "12", "vocabulary": "9"}

empty_publication_data = {
    "title": "",
    "authors": "",
    "open_access_type": "",
    "license": "",
    "publication_state": "",
    "online_publication_date": "",
    "print_publication_date": "",
    "subject_area": "",
    "publication_type": "",
}

valid_publication_data = {
    "title": "Test Title",
    "open_access_type": "Gold",
    "license": "CC_BY",
    "publication_state": "Submitted",
    "online_publication_date": "2021-01-01",
    "print_publication_date": "2021-12-02",
    "subject_area": json.dumps(subject_area),
    "publication_type": json.dumps(publication_type),
}

expected_authors = ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]
author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""


def assert_expected_authors(ctx: dict[str, list[str]]) -> None:
    assert list(ctx["authors"]) == ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]


def parse_authors_request(
    author_str: str, publication_data: dict[str, str] | None = None
) -> HttpRequest:
    return request_factory.post(
        "/",
        (publication_data or empty_publication_data)
        | {"action": "parse_authors", "authors": author_str},
    )


@pytest.mark.django_db
def test__publication_step__action__parse_authors__adds_author_list_to_context() -> None:
    sut = PublicationStep()

    ctx = sut.get_context_data(parse_authors_request(author_str), DictStore())

    assert_expected_authors(ctx)


@pytest.mark.django_db
def test__publication_step__action__parse_authors__does_not_progress() -> None:
    sut = PublicationStep()
    store = DictStore()

    request = parse_authors_request(author_str)
    ctx = sut.get_context_data(request, store)

    assert not sut.is_valid(request, store)
    assert ctx["publication_form"].errors == {}


@pytest.mark.django_db
def test__publication_step__action__parse_authors__retains_posted_data_but_does_not_show_errors() -> (
    None
):
    sut = PublicationStep()
    store = DictStore()

    incomplete_publication_data = dict(valid_publication_data, license="")
    request = parse_authors_request(author_str, incomplete_publication_data)
    ctx = sut.get_context_data(request, store)

    form = ctx["publication_form"]
    assert form.data != {}
    assert form.errors == {}


@pytest.mark.django_db
def test__publication_step__done__saves_authors_to_store() -> None:
    sut = PublicationStep()
    store = DictStore()

    request = parse_authors_request(author_str, valid_publication_data)
    sut.done(request, store)

    assert list(store["authors"]) == expected_authors


@pytest.mark.django_db
def test__publication_step__authors_in_store__get_context_data__contains_authors() -> None:
    sut = PublicationStep()
    store = DictStore()
    store["authors"] = expected_authors

    ctx = sut.get_context_data(request_factory.get("/"), store)

    assert list(ctx["authors"]) == expected_authors


@pytest.mark.django_db
def test__publication_step__authors_in_post_and_store__get_context_data__prefers_post_data() -> (
    None
):
    sut = PublicationStep()
    store = DictStore()
    store["authors"] = ["other authors"]

    request = request_factory.post("/", {"authors": author_str} | valid_publication_data)
    ctx = sut.get_context_data(request, store)

    assert list(ctx["authors"]) == expected_authors
