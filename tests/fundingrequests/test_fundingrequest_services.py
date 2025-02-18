import datetime
import random

import pytest

from coda.apps.fundingrequests import repository, services
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraContactDto, PaymentDto
from coda.apps.fundingrequests.repository import get_by_id
from coda.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    NoContact,
)
from coda.fundingrequests.identity import PublicFundingRequestId
from coda.publication import JournalId
from coda.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.publications.test_publication_repository import assert_publication_eq

_faker = domainfactory._faker


def create_funding() -> ExternalFunding:
    return domainfactory.external_funding(
        FundingOrganizationId(modelfactory.funding_organization().pk)
    )


def extra_contact() -> FilledContact:
    return FilledContact(name=NonEmptyStr(_faker.name()), email=_faker.email())


@pytest.mark.django_db
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data() -> None:
    builder = ArticleRequestDataBuilder()

    new_id = services.create_fundingrequest(
        builder.publication_dto(),
        builder.cost_dto(),
        builder.external_funding_dto(),
        builder.extra_contact_dto(),
    )

    actual = get_by_id(new_id)
    assert_fundingrequest_eq(actual, builder.expected)


@pytest.mark.django_db
def test__create_fundingrequest__id_already_used__retries_with_new_id() -> None:
    builder = ArticleRequestDataBuilder()
    repository.save(builder.expected)

    ids = [builder.expected.request_id, PublicFundingRequestId.create()]
    id_iter = iter(ids)

    def generator(
        date: datetime.date | None = None, rng: random.Random | None = None
    ) -> PublicFundingRequestId:
        return next(id_iter)

    new_id = services.create_fundingrequest(
        builder.publication_dto(),
        builder.cost_dto(),
        builder.external_funding_dto(),
        builder.extra_contact_dto(),
        request_id_generator=generator,
    )

    actual = get_by_id(new_id)
    assert actual.request_id == ids[1]


@pytest.mark.django_db
def test__create_fundingrequest__without_external_funding__creates_fundingrequest() -> None:
    builder = ArticleRequestDataBuilder().without_external_funding()

    new_id = services.create_fundingrequest(
        builder.publication_dto(),
        builder.cost_dto(),
        builder.external_funding_dto(),
        builder.extra_contact_dto(),
    )

    actual = repository.get_by_id(new_id)
    assert list(actual.external_funding) == []


@pytest.mark.django_db
def test__update_fundingrequest__extra_contact__updates_contact_in_database() -> None:
    new_id = repository.save(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )

    new_contact = ExtraContactDto.from_contact(extra_contact())
    services.update_contact(new_id, contact=new_contact)

    updated = get_by_id(new_id)
    assert updated.extra_contact is not None
    assert updated.extra_contact.name == new_contact.name
    assert updated.extra_contact.email == new_contact.email


@pytest.mark.django_db
def test__fundingrequest__empty_extra_contact__fundingrequest_has_no_contact() -> None:
    new_id = repository.save(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )

    services.update_contact(new_id, contact=ExtraContactDto(name="", email=""))

    updated = get_by_id(new_id)
    assert updated.extra_contact is NoContact


@pytest.mark.django_db
def test__update_fundingrequest_cost_and_external_funding__updates_cost_and_external_funding() -> (
    None
):
    new_id = repository.save(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )

    new_cost = domainfactory.payment()
    new_organization = modelfactory.funding_organization()
    new_funding = [domainfactory.external_funding(FundingOrganizationId(new_organization.pk))]

    payment_dto = PaymentDto.from_payment(new_cost)
    funding_dtos = map(ExternalFundingDto.from_external_funding, new_funding)
    services.update_funding(new_id, payment_dto, funding_dtos)

    updated = get_by_id(new_id)
    assert updated.estimated_cost == new_cost
    assert list(updated.external_funding) == list(new_funding)


def assert_fundingrequest_eq(actual: AnyFundingRequest, expected: AnyFundingRequest) -> None:
    assert actual.request_date == expected.request_date
    assert_fundingrequest_contact_eq(actual.extra_contact, expected.extra_contact)

    assert_publication_eq(actual.publication, expected.publication)
    assert actual.estimated_cost == expected.estimated_cost
    assert list(actual.external_funding) == list(expected.external_funding)
    assert actual.review() == expected.review()


def assert_fundingrequest_contact_eq(
    actual: FundingRequestContact, expected: FundingRequestContact
) -> None:
    assert actual == expected
