import datetime
import random
from collections.abc import Callable, Iterable

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.repository import get_by_id
from coda.apps.institutions.models import Institution
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import ContractYearDto, PublicationDto
from coda.apps.publications.repositories import vocabulary_repository
from coda.contexts.fundingrequest import services
from coda.contexts.fundingrequest.dto.commands import (
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
    UpdatePublicationMetadataCommand,
    UpdateReviewDto,
)
from coda.contexts.fundingrequest.services.allowed_vocabularies import (
    InvalidPublicationType,
    InvalidSubjectType,
)
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
from coda.domain.vocabulary import VocabularyConcept
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
    metadata = UpdatePublicationMetadataCommand(
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
    expected_publication.contracts = (contract_year,)

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
def test__fundingrequest__update_reviewer_remarks__updates_remarks_and_keeps_rest_of_review() -> (
    None
):
    new_id = repository.create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )
    repository.save_review(
        Review(new_id, Money(100, Currency.GBP), remarks="old", result=ReviewResult.Approved)
    )

    services.fundingrequests.update_extra_information(
        new_id, ExtraInformationDto(request_remarks="request remarks", reviewer_remarks="new")
    )

    updated = get_by_id(new_id)
    assert updated.request_remarks == "request remarks"
    assert updated.review_remarks == "new"
    assert updated.funding_amount == Money(100, Currency.GBP)
    assert updated.review() == ReviewResult.Approved


@pytest.mark.django_db
def test__fundingrequest__update_extra_info_without_reviewer_remarks__keeps_review_remarks() -> (
    None
):
    new_id = repository.create(
        FundingRequest.new(
            publication=domainfactory.publication(JournalId(modelfactory.journal().pk)),
            extra_contact=extra_contact(),
            estimated_cost=domainfactory.payment(),
        )
    )
    repository.save_review(Review(new_id, remarks="keep me", result=ReviewResult.Approved))

    services.fundingrequests.update_extra_information(
        new_id, ExtraInformationDto(request_remarks="request remarks")
    )

    assert get_by_id(new_id).review_remarks == "keep me"


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


# ---------------------------------------------------------------------------
# Vocabulary validation
# ---------------------------------------------------------------------------

Builder = ArticleRequestDataBuilder | MonographRequestDataBuilder


@pytest.fixture(
    params=[
        ArticleRequestDataBuilder,
        MonographRequestDataBuilder,
    ]
)
def builder(request: pytest.FixtureRequest) -> Builder:
    return request.param()  # type: ignore[no-any-return]


def disallowed_publication_type(builder: Builder) -> VocabularyConcept:
    """Return a concept that is disallowed in the active publication-type vocabulary.

    Adds a second concept to the base vocabulary (the publication keeps concept[0]),
    wraps the base in a LimitedVocabulary that disallows only the second concept,
    and registers it as active.  Because the publication's existing concept[0] is NOT
    disallowed, the grandfather clause in for_existing_publication does not protect
    concept[1] — so an update command using concept[1] correctly raises.
    """
    assert builder.publication_types.id is not None
    builder.publication_types.add_concept("disallowed_concept")
    vocabulary_repository.save(builder.publication_types)
    # Re-fetch so the new concept has a DB-assigned entity_id
    refreshed = vocabulary_repository.get_by_id(builder.publication_types.id)
    disallowed = next(c for c in refreshed.concepts if c.concept_id == "disallowed_concept")
    limited = vocabulary_repository.create_limited(
        builder.publication_types.id, "limited_publication_types"
    )
    limited.disallow(disallowed.concept_id)
    vocabulary_repository.save(limited)
    GlobalPreferences.set_article_publication_type_vocabulary(limited)
    GlobalPreferences.set_monograph_publication_type_vocabulary(limited)
    return disallowed


def disallowed_subject_area(builder: Builder) -> VocabularyConcept:
    """Return a concept that is disallowed in the active subject-area vocabulary.

    Adds a second concept to the base vocabulary (the publication keeps concept[0]),
    wraps the base in a LimitedVocabulary that disallows only the second concept,
    and registers it as active.  Because the publication's existing concept[0] is NOT
    disallowed, the grandfather clause in for_existing_publication does not protect
    concept[1] — so an update command using concept[1] correctly raises.
    """
    assert builder.subject_areas.id is not None
    builder.subject_areas.add_concept("disallowed_concept")
    vocabulary_repository.save(builder.subject_areas)
    # Re-fetch so the new concept has a DB-assigned entity_id
    refreshed = vocabulary_repository.get_by_id(builder.subject_areas.id)
    disallowed = next(c for c in refreshed.concepts if c.concept_id == "disallowed_concept")
    limited = vocabulary_repository.create_limited(
        builder.subject_areas.id, "limited_subject_areas"
    )
    limited.disallow(disallowed.concept_id)
    vocabulary_repository.save(limited)
    GlobalPreferences.set_subject_classification_vocabulary(limited)
    return disallowed


@pytest.mark.django_db
def test__create_fundingrequest__disallowed_publication_type__raises_invalid_publication_type(
    builder: Builder,
) -> None:
    builder.publication.publication_type = disallowed_publication_type(builder)

    with pytest.raises(InvalidPublicationType):
        services.fundingrequests.create_fundingrequest(builder.creation_dto())


@pytest.mark.django_db
def test__create_fundingrequest__disallowed_subject_area__raises_invalid_subject_type(
    builder: Builder,
) -> None:
    builder.publication.subject_area = disallowed_subject_area(builder)

    with pytest.raises(InvalidSubjectType):
        services.fundingrequests.create_fundingrequest(builder.creation_dto())


@pytest.mark.django_db
def test__update_publication_metadata__disallowed_publication_type__raises_invalid_publication_type(
    builder: Builder,
) -> None:
    fr_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    builder.publication.publication_type = disallowed_publication_type(builder)
    dto = builder.publication_dto()
    command = UpdatePublicationMetadataCommand(
        meta=dto.meta,
        relevant_authors=dto.relevant_authors,
        other_authors=dto.other_authors,
        links=dto.links,
    )

    with pytest.raises(InvalidPublicationType):
        services.fundingrequests.update_publication_metadata(fr_id, command)


@pytest.mark.django_db
def test__update_publication_metadata__disallowed_subject_area__raises_invalid_subject_type(
    builder: Builder,
) -> None:
    fr_id = services.fundingrequests.create_fundingrequest(builder.creation_dto())

    builder.publication.subject_area = disallowed_subject_area(builder)
    dto = builder.publication_dto()
    command = UpdatePublicationMetadataCommand(
        meta=dto.meta,
        relevant_authors=dto.relevant_authors,
        other_authors=dto.other_authors,
        links=dto.links,
    )

    with pytest.raises(InvalidSubjectType):
        services.fundingrequests.update_publication_metadata(fr_id, command)
