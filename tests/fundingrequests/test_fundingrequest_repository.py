import pytest

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.services import fundingrequest_create
from tests.fundingrequests import factory


@pytest.mark.django_db
def test__searching_for_funding_requests_by_title__returns_matching_funding_requests() -> None:
    affiliation = factory.institution().pk
    author_dto = factory.valid_author_dto(affiliation)
    journal = factory.journal()

    title = "The Search Term"
    matching_request = create_request_with_title(title, author_dto, journal.pk)

    create_request_with_title("No match", author_dto, journal.pk)
    results = repository.search_by_publication_title(title)

    assert list(results) == [matching_request]


def create_request_with_title(title: str, author_dto: AuthorDto, journal_pk: int) -> FundingRequest:
    matching_publication = factory.publication_dto(journal_pk)
    matching_publication["title"] = title
    matching_request = fundingrequest_create(
        author_dto, matching_publication, factory.funding_dto()
    )

    return matching_request
