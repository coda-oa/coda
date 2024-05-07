import pytest

from coda.apps.authors.dto import parse_author
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import parse_external_funding, parse_payment
from coda.apps.fundingrequests.models import (
    ExternalFunding as ExternalFundingModel,
)
from coda.apps.fundingrequests.models import (
    FundingRequest as FundingRequestModel,
)
from coda.apps.publications.dto import parse_publication
from coda.fundingrequest import FundingRequest, FundingRequestId
from tests import factory
from tests.assertions import (
    assert_correct_funding_request,
    assert_cost_equal,
    assert_external_funding_equal,
)


@pytest.mark.django_db
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data() -> None:
    journal = factory.db_journal().pk
    organization = factory.db_funding_organization()

    author_dto = factory.author_dto(factory.db_institution().pk)
    publication_dto = factory.publication_dto(journal)
    external_funding_dto = factory.external_funding_dto(organization.pk)
    cost_dto = factory.cost_dto()

    services.fundingrequest_create(
        FundingRequest(
            id=None,
            publication=parse_publication(publication_dto),
            submitter=parse_author(author_dto),
            estimated_cost=parse_payment(cost_dto),
            external_funding=parse_external_funding(external_funding_dto),
        )
    )

    assert_correct_funding_request(author_dto, publication_dto, external_funding_dto, cost_dto)


@pytest.mark.django_db
def test__create_fundingrequest__without_external_funding__creates_fundingrequest() -> None:
    author_dto = factory.author_dto(factory.db_institution().pk)
    journal = factory.db_journal().pk
    publication_dto = factory.publication_dto(journal)
    cost_dto = factory.cost_dto()

    request_id = services.fundingrequest_create(
        FundingRequest(
            id=None,
            publication=parse_publication(publication_dto),
            submitter=parse_author(author_dto),
            estimated_cost=parse_payment(cost_dto),
            external_funding=None,
        )
    )

    request = FundingRequestModel.objects.get(pk=request_id)
    assert request.external_funding is None


@pytest.mark.django_db
def test__update_fundingrequest_cost_and_external_funding__updates_cost_and_external_funding() -> (
    None
):
    request = factory.fundingrequest()
    new_organization = factory.db_funding_organization()
    new_cost_dto = factory.cost_dto()
    new_funding_dto = factory.external_funding_dto(new_organization.pk)
    new_cost = parse_payment(new_cost_dto)
    new_funding = parse_external_funding(new_funding_dto)

    services.fundingrequest_funding_update(FundingRequestId(request.pk), new_cost, new_funding)

    request.refresh_from_db()
    assert_cost_equal(new_cost_dto, request)
    assert_external_funding_equal(new_funding_dto, request)


@pytest.mark.django_db
def test__update_fundingrequest_funding__deletes_old_external_funding() -> None:
    request = factory.fundingrequest()
    new_cost_dto = factory.cost_dto()
    new_organization = factory.db_funding_organization()
    new_funding_dto = factory.external_funding_dto(new_organization.pk)
    new_cost = parse_payment(new_cost_dto)
    new_funding = parse_external_funding(new_funding_dto)

    services.fundingrequest_funding_update(FundingRequestId(request.pk), new_cost, new_funding)

    assert ExternalFundingModel.objects.count() == 1


@pytest.mark.django_db
def test__update_fundingrequest_funding__without_external_funding__deletes_old_external_funding() -> (
    None
):
    request = factory.fundingrequest()
    new_cost = parse_payment(factory.cost_dto())
    new_funding = None

    services.fundingrequest_funding_update(FundingRequestId(request.pk), new_cost, new_funding)

    request.refresh_from_db()
    assert request.external_funding is None
    assert ExternalFundingModel.objects.count() == 0
