import pytest

from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.repository import get_by_id
from coda.author import InstitutionId
from coda.fundingrequest import FundingOrganizationId, FundingRequest
from coda.publication import JournalId
from tests import domainfactory, modelfactory
from tests.authors.test__author import assert_author_eq
from tests.publications.test_publication_services import assert_publication_eq


@pytest.mark.django_db
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data() -> None:
    expected = FundingRequest.new(
        publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
        submitter=domainfactory.author(InstitutionId(modelfactory.institution().pk)),
        estimated_cost=domainfactory.payment(),
        external_funding=domainfactory.external_funding(
            FundingOrganizationId(modelfactory.funding_organization().pk)
        ),
    )

    new_id = services.fundingrequest_create(expected)

    actual = get_by_id(new_id)
    assert_fundingrequest_eq(actual, expected)


@pytest.mark.django_db
def test__create_fundingrequest__without_external_funding__creates_fundingrequest() -> None:
    new_id = services.fundingrequest_create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            submitter=domainfactory.author(InstitutionId(modelfactory.institution().pk)),
            estimated_cost=domainfactory.payment(),
            external_funding=None,
        )
    )

    actual = get_by_id(new_id)
    assert actual.external_funding is None


@pytest.mark.django_db
def test__update_fundingrequest_cost_and_external_funding__updates_cost_and_external_funding() -> (
    None
):
    new_id = services.fundingrequest_create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            submitter=domainfactory.author(InstitutionId(modelfactory.institution().pk)),
            estimated_cost=domainfactory.payment(),
            external_funding=None,
        )
    )

    new_cost = domainfactory.payment()
    new_organization = modelfactory.funding_organization()
    new_funding = domainfactory.external_funding(FundingOrganizationId(new_organization.pk))
    services.fundingrequest_funding_update(new_id, new_cost, new_funding)

    updated = get_by_id(new_id)
    assert updated.estimated_cost == new_cost
    assert updated.external_funding == new_funding


@pytest.mark.django_db
def test__update_fundingrequest_funding__deletes_old_external_funding() -> None:
    new_id = services.fundingrequest_create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            submitter=domainfactory.author(InstitutionId(modelfactory.institution().pk)),
            estimated_cost=domainfactory.payment(),
            external_funding=None,
        )
    )

    services.fundingrequest_funding_update(
        new_id,
        domainfactory.payment(),
        domainfactory.external_funding(
            FundingOrganizationId(modelfactory.funding_organization().pk)
        ),
    )

    assert ExternalFundingModel.objects.count() == 1


@pytest.mark.django_db
def test__update_fundingrequest_funding__without_external_funding__deletes_old_external_funding() -> (
    None
):
    new_id = services.fundingrequest_create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            submitter=domainfactory.author(InstitutionId(modelfactory.institution().pk)),
            estimated_cost=domainfactory.payment(),
            external_funding=None,
        )
    )

    new_funding = None
    services.fundingrequest_funding_update(new_id, domainfactory.payment(), new_funding)

    updated = get_by_id(new_id)
    assert updated.external_funding is None
    assert ExternalFundingModel.objects.count() == 0


def assert_fundingrequest_eq(actual: FundingRequest, expected: FundingRequest) -> None:
    assert_author_eq(actual.submitter, expected.submitter)
    assert_publication_eq(actual.publication, expected.publication)
    assert actual.estimated_cost == expected.estimated_cost
    assert actual.external_funding == expected.external_funding
    assert actual.review() == expected.review()
