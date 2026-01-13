import datetime
import random
from collections.abc import Callable, Iterable

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository, services
from coda.apps.fundingrequests.dto import (
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
    UpdateReviewDto,
)
from coda.apps.fundingrequests.repository import get_by_id
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStepDto
from coda.apps.institutions.models import Institution
from coda.apps.publications.dto import ContractYearDto, PublicationDto
from coda.domain.author import InstitutionId
from coda.domain.date import DateRange
from coda.domain.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    NoContact,
    PublicFundingRequestId,
)
from coda.domain.fundingrequest.review import Review, ReviewResult
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication import JournalId
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder
from tests.publications.test_publication_repository import assert_publication_eq

_faker = domainfactory._faker


def create_funding() -> ExternalFunding:
    return domainfactory.external_funding(
        FundingOrganizationId(modelfactory.funding_organization().pk)
    )


def extra_contact() -> FilledContact:
    return FilledContact(name=NonEmptyStr(_faker.name()), email=_faker.email())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "get_builder",
    [lambda: ArticleRequestDataBuilder(), lambda: MonographRequestDataBuilder()],
)
def test__create_fundingrequest__creates_a_fundingrequest_based_on_given_data(
    get_builder: Callable[[], ArticleRequestDataBuilder | MonographRequestDataBuilder],
) -> None:
    builder = get_builder()

    new_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    actual = get_by_id(new_id)
    assert_fundingrequest_eq(actual, builder.expected)


@pytest.mark.django_db
def test__create_fundingrequest__id_already_used__retries_with_new_id() -> None:
    builder = ArticleRequestDataBuilder()
    repository.create(builder.expected)

    ids = [builder.expected.request_id, PublicFundingRequestId.create()]
    id_iter = iter(ids)

    def generator(
        date: datetime.date | None = None, rng: random.Random | None = None
    ) -> PublicFundingRequestId:
        return next(id_iter)

    new_id = services.fundingrequests.create_fundingrequest(
        builder.creation_dto(), request_id_generator=generator
    )

    actual = get_by_id(new_id)
    assert actual.request_id == ids[1]


@pytest.mark.django_db
def test__fundingrequest__publication_with_same_contract_in_different_years__create_fundingrequest__creates_fundingrequest_with_both_contracts() -> (
    None
):
    contract = domainfactory.contract(period=DateRange.create(start=datetime.date(2023, 1, 1)))
    contract.id = contract_repository.create(contract)

    first = contract.in_year(2023)
    second = contract.in_year(2024)

    builder = ArticleRequestDataBuilder().with_contracts([first, second])
    new_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    actual = get_by_id(new_id)
    assert_fundingrequest_eq(actual, builder.expected)


@pytest.mark.django_db
def test__create_fundingrequest__without_external_funding__creates_fundingrequest() -> None:
    builder = ArticleRequestDataBuilder().without_external_funding()

    new_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    actual = repository.get_by_id(new_id)
    assert list(actual.external_funding) == []


@pytest.mark.django_db
def test__update_publication_metadata__updates_metadata_only() -> None:
    """Test that metadata updates don't affect contracts/journal"""
    builder = ArticleRequestDataBuilder()
    fr_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())
    original_fr = repository.get_article_request(fr_id)

    new_builder = builder.with_new_publication(original_fr.publication.id)
    dto = PublicationDto.from_publication(new_builder.publication)
    metadata = PublicationStepDto(
        meta=dto.meta,
        relevant_authors=dto.relevant_authors,
        other_authors=dto.other_authors,
        links=dto.links,
    )

    expected_publication = new_builder.publication
    expected_publication.contracts = original_fr.publication.contracts
    expected_publication.journal = original_fr.publication.journal

    expected_fr = FundingRequest(
        id=original_fr.id,
        request_id=original_fr.request_id,
        publication=expected_publication,
        estimated_cost=original_fr.estimated_cost,
        legacy_request_id=original_fr.legacy_request_id,
        external_funding=original_fr.external_funding,
        extra_contact=original_fr.extra_contact,
        request_remarks=original_fr.request_remarks,
        review=original_fr._review,
    )

    services.fundingrequests.update_publication_metadata(fr_id, metadata)

    updated = get_by_id(fr_id)
    assert_fundingrequest_eq(updated, expected_fr)


@pytest.mark.django_db
def test__update_publication_journal_and_contracts__updates_journal_and_contracts() -> None:
    """Test that journal and contracts can be updated together"""
    builder = ArticleRequestDataBuilder()
    fr_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    new_journal = JournalId(modelfactory.journal().pk)

    new_contract = domainfactory.contract()
    new_contract.id = contract_repository.create(new_contract)
    contract_year = new_contract.in_first_year()
    contract_dtos = [ContractYearDto.from_contract_year(contract_year)]

    expected_fundingrequest = repository.get_article_request(fr_id)
    expected_publication = expected_fundingrequest.publication
    expected_publication.journal = new_journal
    expected_publication.contracts = tuple([contract_year])

    services.fundingrequests.update_publication_journal_and_contracts(
        fr_id, new_journal, contract_dtos
    )

    updated = repository.get_article_request(fr_id)
    assert_fundingrequest_eq(updated, expected_fundingrequest)


@pytest.mark.django_db
def test__fundingrequest__publication_with_same_contract_in_different_years__update_with_one_contract_removed__removes_contract_from_publication() -> (
    None
):
    contract = domainfactory.contract(period=DateRange.create(start=datetime.date(2023, 1, 1)))
    contract.id = contract_repository.create(contract)

    first = contract.in_year(2023)
    second = contract.in_year(2024)

    builder = ArticleRequestDataBuilder().with_contracts([first, second])
    new_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    original_fr = repository.get_article_request(new_id)
    contract_dtos = [ContractYearDto.from_contract_year(first)]
    services.fundingrequests.update_publication_journal_and_contracts(
        new_id, original_fr.publication.journal, contract_dtos
    )

    updated = get_by_id(new_id)
    assert len(updated.publication.contracts) == 1
    assert updated.publication.contracts[0].year == first.year


@pytest.mark.django_db
def test__fundingrequest__update_with_empty_extra_contact__fundingrequest_has_no_contact() -> None:
    new_id = repository.create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )

    services.fundingrequests.update_extra_information(
        new_id, ExtraInformationDto(extra_contact=ExtraContactDto())
    )

    updated = get_by_id(new_id)
    assert updated.extra_contact is NoContact


@pytest.mark.django_db
def test__fundingrequest__update_request_remarks__is_saved_to_db() -> None:
    new_id = repository.create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )

    new_remarks = _faker.sentence()
    services.fundingrequests.update_extra_information(
        new_id, ExtraInformationDto(request_remarks=new_remarks)
    )

    updated = get_by_id(new_id)
    assert updated.request_remarks == new_remarks


@pytest.mark.django_db
def test__update_fundingrequest_cost_and_external_funding__updates_cost_and_external_funding() -> (
    None
):
    new_id = repository.create(
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
    services.fundingrequests.update_funding(new_id, payment_dto, funding_dtos)

    updated = get_by_id(new_id)
    assert updated.estimated_cost == new_cost
    assert list(updated.external_funding) == list(new_funding)


@pytest.mark.django_db
def test__update_fundingrequest_review__updates_the_review() -> None:
    new_id = repository.create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            estimated_cost=domainfactory.payment(),
        )
    )

    review = Review(
        new_id,
        Money(100, Currency.GBP),
        remarks="Something interesing",
        result=ReviewResult.Approved,
    )
    dto = UpdateReviewDto(
        decided_funding_amount=float(review.decided_funding.amount),
        decided_funding_currency=review.decided_funding.currency.code,
        reviewer_remarks=review.remarks,
        result=review.result.value,
    )

    services.fundingrequests.update_review(new_id, dto)

    fr = repository.get_by_id(new_id)
    assert fr.review() == review.result
    assert fr.review_remarks == review.remarks


@pytest.mark.django_db
def test__get_institutions__returns_enabled_institutions() -> None:
    enabled = modelfactory.institution(enabled=True)
    disabled = modelfactory.institution(enabled=False)  # noqa

    institutions = services.fundingrequests.get_institutions_allowed_as_affiliation()

    assert list(institutions) == [enabled]


@pytest.mark.django_db
def test__authors_with_disabled_institutions_as_affiliation__get_institutions__returns_enabled_institutions_and_currently_set_disabled_institution() -> (
    None
):
    enabled = modelfactory.institution(enabled=True)
    disabled_affiliation_1 = modelfactory.institution(enabled=False)
    disabled_affiliation_2 = modelfactory.institution(enabled=False)
    should_not_include = modelfactory.institution(enabled=False)  # noqa

    first_author = domainfactory.author(affiliation=InstitutionId(disabled_affiliation_1.pk))
    second_author = domainfactory.author(affiliation=InstitutionId(disabled_affiliation_2.pk))

    institutions = services.fundingrequests.get_institutions_allowed_as_affiliation(
        for_authors=[first_author, second_author]
    )

    expected_institutions = [enabled, disabled_affiliation_1, disabled_affiliation_2]
    assert_contains_expected_institutions(institutions, expected_institutions)


@pytest.mark.django_db
def test__author_with_enabled_institution_as_affiliation__get_institutions__returns_enabled_institutions_without_duplicates() -> (
    None
):
    affiliation = modelfactory.institution(enabled=True)
    author = domainfactory.author(affiliation=InstitutionId(affiliation.pk))

    institutions = services.fundingrequests.get_institutions_allowed_as_affiliation(
        for_authors=[author]
    )

    assert_contains_expected_institutions(institutions, [affiliation])


def assert_contains_expected_institutions(
    actual: Iterable[Institution], expected: Iterable[Institution]
) -> None:
    expected_institution_set = set(expected)
    actual_tuple = tuple(actual)
    assert len(actual_tuple) == len(expected_institution_set)
    assert set(actual_tuple) == expected_institution_set


def assert_fundingrequest_eq(actual: AnyFundingRequest | None, expected: AnyFundingRequest) -> None:
    assert actual is not None
    assert actual.request_date == expected.request_date
    assert actual.legacy_request_id == expected.legacy_request_id

    assert_publication_eq(actual.publication, expected.publication)
    assert actual.estimated_cost == expected.estimated_cost
    assert list(actual.external_funding) == list(expected.external_funding)
    assert actual.review() == expected.review()
    assert_fundingrequest_contact_eq(actual.extra_contact, expected.extra_contact)
    assert actual.request_remarks == expected.request_remarks


def assert_fundingrequest_contact_eq(
    actual: FundingRequestContact, expected: FundingRequestContact
) -> None:
    assert actual == expected
