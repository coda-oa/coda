import pytest

from coda.author import Author, AuthorId
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    FundingRequestLocked,
    Payment,
    PaymentMethod,
    Review,
)
from coda.money import Currency, Money
from coda.publication import JournalId, Publication, PublicationId
from coda.string import NonEmptyStr


def make_sut() -> FundingRequest:
    sut = FundingRequest(
        id=FundingRequestId(8),
        publication=Publication(
            id=PublicationId(8),
            title=NonEmptyStr("Publication Title"),
            journal=JournalId(3),
        ),
        submitter=Author(AuthorId(1), NonEmptyStr("John Doe")),
        estimated_cost=Payment(
            Money(100, Currency.EUR),
            PaymentMethod.Direct,
        ),
        external_funding=ExternalFunding(
            organization=FundingOrganizationId(1),
            project_id=NonEmptyStr("123"),
            project_name="Project Name",
        ),
    )

    return sut


@pytest.fixture(params=[Review.Rejected, Review.Approved])
def closed_request(request: pytest.FixtureRequest) -> FundingRequest:
    status: Review = request.param
    sut = make_sut()
    sut.add_review(status)
    return sut


def test__new_fundingrequest__has_open_review() -> None:
    sut = make_sut()

    assert sut.review() == Review.Open


def test__open_fundingrequest__add_approved_review__changes_status_to_approved() -> None:
    sut = make_sut()

    sut.add_review(Review.Approved)

    assert sut.review() == Review.Approved


def test__open_fundingrequest__reject__changes_status_to_rejected() -> None:
    sut = make_sut()

    sut.add_review(Review.Rejected)

    assert sut.review() == Review.Rejected


def test__approved_fundingrequest__add_review__cannot_change_status() -> None:
    sut = make_sut()

    sut.add_review(Review.Approved)

    with pytest.raises(FundingRequestLocked):
        sut.add_review(Review.Rejected)

    assert sut.review() == Review.Approved


def test__rejected_fundingrequest__approve__cannot_change_status() -> None:
    sut = make_sut()
    sut.add_review(Review.Rejected)

    with pytest.raises(FundingRequestLocked):
        sut.add_review(Review.Approved)

    assert sut.review() == Review.Rejected


def test__rejected_fundingrequest__open__changes_status_to_open(
    closed_request: FundingRequest,
) -> None:
    sut = closed_request

    sut.open()

    assert sut.review() == Review.Open


def test__closed_fundingrequest__changing_publication__raises_error(
    closed_request: FundingRequest,
) -> None:
    sut = closed_request
    old_journal = sut.publication.journal

    with pytest.raises(FundingRequestLocked):
        sut.publication = new_publication()

    assert sut.publication.journal == old_journal


def test__closed_fundingrequest__changing_submitter__raises_error(
    closed_request: FundingRequest,
) -> None:
    sut = closed_request

    with pytest.raises(FundingRequestLocked):
        sut.submitter = Author(AuthorId(2), NonEmptyStr("Jane Doe"))

    assert sut.submitter.id == AuthorId(1)
    assert sut.submitter.name == NonEmptyStr("John Doe")


def test__closed_then_reopened_fundingrequest__can_change_publication_again(
    closed_request: FundingRequest,
) -> None:
    sut = closed_request
    sut.open()

    sut.publication = new_publication()

    assert sut.publication == new_publication()


def test__closed_fundingrequest__is_open__is_false(closed_request: FundingRequest) -> None:
    sut = closed_request
    assert not sut.is_open()


def new_publication() -> Publication:
    return Publication(
        id=PublicationId(999), title=NonEmptyStr("Publication Title"), journal=JournalId(999)
    )
