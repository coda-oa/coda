import pytest

from coda.apps.fundingrequests import services
from tests.fundingrequests import factory
from tests.fundingrequests.assertions import assert_correct_funding_request


@pytest.mark.django_db
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data() -> None:
    author = factory.valid_author_dto(factory.institution().pk)
    journal = factory.journal().pk
    publication = factory.publication_dto(journal)
    funding = factory.funding_dto()

    services.fundingrequest_create(author, publication, funding)

    assert_correct_funding_request(author, publication, funding)
