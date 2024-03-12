import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.views import FundingRequestListView
from tests.fundingrequests import factory
from tests.fundingrequests.test_fundingrequest_repository import create_request_with_title
from tests.fundingrequests.test_fundingrequest_labels import logged_in  # noqa: F401


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_title__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    affiliation = factory.institution().pk
    author_dto = factory.valid_author_dto(affiliation)
    journal = factory.journal()

    title = "The Search Term"
    matching_request = create_request_with_title(title, author_dto, journal.pk)
    create_request_with_title("No match", author_dto, journal.pk)

    response = client.get(reverse("fundingrequests:list"), data={"title": title})

    assert response.context[FundingRequestListView.context_object_name] == [matching_request]
