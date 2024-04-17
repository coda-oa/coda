from django.http import HttpRequest
from django.test import RequestFactory

from coda.apps.fundingrequests.wizardsteps import PublicationStep
from tests.test_wizard import DictStore

request_factory = RequestFactory()

empty_publication_data = {
    "title": "",
    "authors": "",
    "open_access_type": "",
    "license": "",
    "publication_state": "",
    "publication_date": "",
}

valid_publication_data = {
    "title": "Test Title",
    "open_access_type": "GOLD",
    "license": "CC_BY",
    "publication_state": "published",
    "publication_date": "2021-01-01",
}


def parse_authors_request(
    author_str: str, publication_data: dict[str, str] | None = None
) -> HttpRequest:
    return request_factory.post(
        "/",
        (publication_data or empty_publication_data)
        | {"action": "parse_authors", "authors": author_str},
    )


def test__publication_step__action__parse_authors__adds_author_list_to_context() -> None:
    sut = PublicationStep()
    author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""

    ctx = sut.get_context_data(parse_authors_request(author_str), DictStore())

    assert ctx["authors"] == ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]


def test__publication_step__action__parse_authors__does_not_progress() -> None:
    sut = PublicationStep()
    store = DictStore()
    author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""

    request = parse_authors_request(author_str)
    ctx = sut.get_context_data(request, store)

    assert not sut.is_valid(request, store)
    assert ctx["publication_form"].errors == {}


def test__publication_step__action__parse_authors__retains_posted_data_but_does_not_show_errors() -> (
    None
):
    sut = PublicationStep()
    store = DictStore()
    author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""

    incomplete_publication_data = dict(valid_publication_data, license="")
    request = parse_authors_request(author_str, incomplete_publication_data)
    ctx = sut.get_context_data(request, store)

    form = ctx["publication_form"]
    assert form.data != {}
    assert form.errors == {}


def test__publication_step__done__saves_authors_to_store() -> None:
    sut = PublicationStep()
    store = DictStore()
    author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""

    request = parse_authors_request(author_str, valid_publication_data)
    sut.done(request, store)

    assert store["authors"] == ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]
