import pytest

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Role
from coda.apps.fundingrequests import services
from tests import test_orcid
from tests.fundingrequests import factory
from tests.fundingrequests.assertions import assert_correct_funding_request, assert_author_equal


@pytest.mark.django_db
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data() -> None:
    author = factory.valid_author_dto(factory.institution().pk)
    journal = factory.journal().pk
    publication = factory.publication_dto(journal)
    organization = factory.funding_organization()
    external_funding = factory.external_funding_dto(organization.pk)
    cost = factory.cost_dto()

    services.fundingrequest_create(author, publication, external_funding, cost)

    assert_correct_funding_request(author, publication, external_funding, cost)


@pytest.mark.django_db
def test__update_fundingrequest_submitter__updates_submitter() -> None:
    request = factory.fundingrequest()
    affiliation = factory.institution()

    new_author = AuthorDto(
        name="New Author",
        email="newauthor@mail.com",
        affiliation=affiliation.pk,
        orcid=test_orcid.LAUREL_HAAK,
        roles=[Role.CO_AUTHOR.name],
    )

    services.fundingrequest_submitter_update(request.pk, new_author)

    request.refresh_from_db()
    assert_author_equal(new_author, request.submitter)
