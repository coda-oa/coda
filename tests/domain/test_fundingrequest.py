import pytest

from coda.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
    PaymentMethod,
    ReviewResult,
)
from coda.money import Currency, Money
from coda.publication import JournalId, Publication, PublicationId
from coda.string import NonEmptyStr


def make_sut() -> FundingRequest[Publication]:
    sut = FundingRequest(
        id=FundingRequestId(8),
        publication=Publication(
            id=PublicationId(8),
            title=NonEmptyStr("Publication Title"),
            journal=JournalId(3),
        ),
        extra_contact=FilledContact(NonEmptyStr("John Doe"), "j.doe@example.com"),
        estimated_cost=Payment(
            Money(100, Currency.EUR),
            PaymentMethod.Direct,
        ),
        external_funding=[
            ExternalFunding(
                organization=FundingOrganizationId(1),
                project_id=NonEmptyStr("123"),
                project_name="Project Name",
            )
        ],
    )

    return sut


@pytest.fixture(params=[ReviewResult.Rejected, ReviewResult.Approved])
def closed_request(request: pytest.FixtureRequest) -> FundingRequest[Publication]:
    status: ReviewResult = request.param
    sut = make_sut()
    if status == ReviewResult.Rejected:
        sut.reject("Rejected")
    else:
        sut.approve(Money(100, Currency.EUR), "Approved")

    return sut


def test__new_fundingrequest__has_open_review() -> None:
    sut = make_sut()

    assert sut.review() == ReviewResult.Open


def test__open_fundingrequest__add_approved_review__changes_status_to_approved() -> None:
    sut = make_sut()

    sut.approve(Money(100, Currency.EUR), "Approved")

    assert sut.review() == ReviewResult.Approved
    assert sut.funding_amount == Money(100, Currency.EUR)
    assert sut.review_remarks == "Approved"


def test__open_fundingrequest__reject__changes_status_to_rejected() -> None:
    sut = make_sut()

    sut.reject("Rejected")

    assert sut.review() == ReviewResult.Rejected
    assert sut.review_remarks == "Rejected"
    assert sut.funding_amount == Money(0, Currency.EUR)


def test__rejected_fundingrequest__open__changes_status_to_open(
    closed_request: FundingRequest[Publication],
) -> None:
    sut = closed_request

    sut.open("Reopened")

    assert sut.review() == ReviewResult.Open
    assert sut.review_remarks == "Reopened"


def test__approved_fundingrequest__open__keeps_funding_amount() -> None:
    sut = make_sut()
    sut.approve(Money(100, Currency.EUR), "A Comment")

    sut.open()

    assert sut.review() == ReviewResult.Open
    assert sut.funding_amount == Money(100, Currency.EUR)


def test__closed_fundingrequest__is_open__is_false(
    closed_request: FundingRequest[Publication],
) -> None:
    sut = closed_request
    assert not sut.is_open()


def test__fundingrequest__waive_costs__is_closed_without_funding() -> None:
    sut = make_sut()
    sut.waive_costs("publisher waived costs")

    assert sut.costs_waived()
    assert not sut.is_open()
    assert not sut.is_rejected()
    assert not sut.is_approved()

    assert sut.funding_amount == Money(0, Currency.EUR)


def test__fundingrequest__close__is_closed_without_funding() -> None:
    sut = make_sut()
    sut.close("Closed")

    assert not sut.is_open()
    assert not sut.is_rejected()
    assert not sut.is_approved()

    assert sut.funding_amount == Money(0, Currency.EUR)


def new_publication() -> Publication:
    return Publication(
        id=PublicationId(999),
        title=NonEmptyStr("Publication Title"),
        journal=JournalId(999),
    )
