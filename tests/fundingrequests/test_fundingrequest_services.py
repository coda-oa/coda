import pytest

from coda.apps.authors.dto import parse_author
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.models import ExternalFunding
from coda.apps.publications.dto import parse_publication
from tests import factory
from tests.assertions import (
    assert_correct_funding_request,
    assert_cost_equal,
    assert_external_funding_equal,
)


@pytest.mark.django_db
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data() -> None:
    author_dto = factory.author_dto(factory.db_institution().pk)
    author = parse_author(author_dto)

    journal = factory.db_journal().pk
    organization = factory.db_funding_organization()

    publication_dto = factory.publication_dto(journal)
    publication = parse_publication(publication_dto)
    external_funding_dto = factory.external_funding_dto(organization.pk)
    cost_dto = factory.cost_dto()

    services.fundingrequest_create(author, publication, external_funding_dto, cost_dto)

    assert_correct_funding_request(author_dto, publication_dto, external_funding_dto, cost_dto)


@pytest.mark.django_db
def test__create_fundingrequest__without_external_funding__creates_fundingrequest() -> None:
    author_dto = factory.author_dto(factory.db_institution().pk)
    author = parse_author(author_dto)
    journal = factory.db_journal().pk
    publication_dto = factory.publication_dto(journal)
    publication = parse_publication(publication_dto)
    cost_dto = factory.cost_dto()

    request = services.fundingrequest_create(author, publication, None, cost_dto)

    assert request.external_funding is None


@pytest.mark.django_db
def test__update_fundingrequest_cost_and_external_funding__updates_cost_and_external_funding() -> (
    None
):
    request = factory.fundingrequest()
    new_cost = factory.cost_dto()
    new_organization = factory.db_funding_organization()
    new_funding = factory.external_funding_dto(new_organization.pk)

    services.fundingrequest_funding_update(request, new_funding, new_cost)

    request.refresh_from_db()
    assert_cost_equal(new_cost, request)
    assert_external_funding_equal(new_funding, request)


@pytest.mark.django_db
def test__update_fundingrequest_funding__deletes_old_external_funding() -> None:
    request = factory.fundingrequest()
    new_cost = factory.cost_dto()
    new_organization = factory.db_funding_organization()
    new_funding = factory.external_funding_dto(new_organization.pk)

    services.fundingrequest_funding_update(request, new_funding, new_cost)

    assert ExternalFunding.objects.count() == 1


@pytest.mark.django_db
def test__update_fundingrequest_funding__without_external_funding__deletes_old_external_funding() -> (
    None
):
    request = factory.fundingrequest()
    new_cost = factory.cost_dto()
    new_funding = None

    services.fundingrequest_funding_update(request, new_funding, new_cost)

    request.refresh_from_db()
    assert request.external_funding is None
    assert ExternalFunding.objects.count() == 0
