from typing import cast
import pytest

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author, PersonId, Role
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.models import ExternalFunding, FundingRequest
from coda.apps.institutions.models import Institution
from tests import test_orcid
from tests.fundingrequests import factory
from tests.fundingrequests.assertions import (
    assert_correct_funding_request,
    assert_author_equal,
    assert_cost_equal,
    assert_external_funding_equal,
    assert_publication_equal,
)


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


@pytest.mark.django_db
def test__update_fundingrequest_publication__updates_publication() -> None:
    request = factory.fundingrequest()
    new_journal = factory.journal()
    links = factory.link_dtos()
    new_publication = factory.publication_dto(new_journal.pk, links=links)

    services.fundingrequest_publication_update(request.pk, new_publication)

    request.refresh_from_db()
    assert_publication_equal(new_publication, author_dto_from_request(request), request.publication)


@pytest.mark.django_db
def test__update_fundingrequest_cost_and_external_funding__updates_cost_and_external_funding() -> (
    None
):
    request = factory.fundingrequest()
    new_cost = factory.cost_dto()
    new_organization = factory.funding_organization()
    new_funding = factory.external_funding_dto(new_organization.pk)

    services.fundingrequest_funding_update(request.pk, new_funding, new_cost)

    request.refresh_from_db()
    assert_cost_equal(new_cost, request)
    assert_external_funding_equal(new_funding, request)


@pytest.mark.django_db
def test__update_fundingrequest_funding__deletes_old_external_funding() -> None:
    request = factory.fundingrequest()
    new_cost = factory.cost_dto()
    new_organization = factory.funding_organization()
    new_funding = factory.external_funding_dto(new_organization.pk)

    services.fundingrequest_funding_update(request.pk, new_funding, new_cost)

    assert ExternalFunding.objects.count() == 1


def author_dto_from_request(request: FundingRequest) -> AuthorDto:
    submitter = cast(Author, request.submitter)
    affiliation = cast(Institution, submitter.affiliation)
    identifier = cast(PersonId, submitter.identifier)
    return AuthorDto(
        name=submitter.name,
        email=str(submitter.email),
        affiliation=affiliation.pk,
        orcid=identifier.orcid,
        roles=[r.name for r in submitter.get_roles()],
    )
