import datetime

from coda.fundingrequest import Review
from coda.fundingrequest import FundingRequest
from coda.fundingrequest.identity import PublicFundingRequestId
from coda.fundingrequest.review import ReviewResult
from coda.money import Currency, Money
from coda.publication import JournalId, Publication, PublicationId
from coda.string import NonEmptyStr
from tests import domainfactory


def make_sut(review: Review | None = None) -> FundingRequest[Publication]:
    return domainfactory.fundingrequest(review=review)


def test__fundingrequest__date_of_request_id__is_date_of_fundingrequest() -> None:
    date = datetime.date(2024, 9, 6)
    request_id = PublicFundingRequestId.create(date)
    sut = FundingRequest.new(
        request_id=request_id,
        publication=domainfactory.publication(),
        estimated_cost=domainfactory.payment(),
    )

    assert sut.request_date == date


def test__new_fundingrequest__has_open_review() -> None:
    sut = make_sut()

    assert sut.review() == ReviewResult.Open


def test__approved_fundingrequest__is_approved_and_not_open() -> None:
    sut = make_sut(
        Review(
            decided_funding=Money(100, Currency.EUR),
            result=ReviewResult.Approved,
            remarks="Approved",
        )
    )

    assert sut.is_approved()
    assert not sut.is_open()


def test__rejected_fundingrequest__is_rejected_and_not_open() -> None:
    sut = make_sut(Review(result=ReviewResult.Rejected, remarks="Rejected"))

    assert sut.is_rejected()
    assert not sut.is_open()


def test__fundingrequest_with_waived_costs__is_not_open_approved_or_rejected() -> None:
    sut = make_sut(
        Review(
            result=ReviewResult.Waived,
            remarks="Waived",
        )
    )

    assert sut.costs_waived()
    assert not sut.is_open()
    assert not sut.is_rejected()
    assert not sut.is_approved()

    assert sut.funding_amount == Money(0, Currency.EUR)


def test__closed_fundingrequest__is_not_open() -> None:
    sut = make_sut(
        Review(
            result=ReviewResult.Closed,
            remarks="Closed",
        )
    )

    assert not sut.is_open()
    assert not sut.is_rejected()
    assert not sut.is_approved()


def new_publication() -> Publication:
    return Publication(
        id=PublicationId(999),
        title=NonEmptyStr("Publication Title"),
        journal=JournalId(999),
    )
