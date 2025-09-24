from coda.domain.fundingrequest import FundingRequestId, Review, ReviewResult
from coda.domain.money import Currency, Money


def make_sut() -> Review:
    return Review(FundingRequestId(1))


def test__open_fundingrequest__add_approved_review__changes_status_to_approved() -> None:
    sut = make_sut()

    sut = sut.update_review(ReviewResult.Approved, Money(100, Currency.EUR), "Approved")

    assert sut.result == ReviewResult.Approved
    assert sut.decided_funding == Money(100, Currency.EUR)
    assert sut.remarks == "Approved"


def test__open_fundingrequest__reject__changes_status_to_rejected() -> None:
    sut = make_sut()

    sut = sut.update_review(ReviewResult.Rejected, Money(0, Currency.EUR), "Rejected")

    assert sut.result == ReviewResult.Rejected
    assert sut.decided_funding == Money(0, Currency.EUR)
    assert sut.remarks == "Rejected"


def test__rejected_fundingrequest__open__changes_status_to_open() -> None:
    sut = make_sut().update_review(ReviewResult.Rejected)

    sut = sut.update_review(ReviewResult.Open, remarks="Reopened")

    assert sut.result == ReviewResult.Open
    assert sut.remarks == "Reopened"


def test__approved_fundingrequest__open__keeps_funding_amount() -> None:
    sut = make_sut().update_review(ReviewResult.Approved, Money(100, Currency.EUR), "A Comment")

    sut = sut.update_review(ReviewResult.Open, remarks="Reopened")

    assert sut.result == ReviewResult.Open
    assert sut.decided_funding == Money(100, Currency.EUR)


def test__open_review__costs_waived__changes_status_to_waived_with_zero_funding() -> None:
    sut = make_sut()

    sut = sut.update_review(ReviewResult.Waived, remarks="Waived")

    assert sut.result == ReviewResult.Waived
    assert sut.decided_funding == Money(0, Currency.EUR)
    assert sut.remarks == "Waived"


def test__open_review__closed__changes_status_to_closed() -> None:
    sut = make_sut()

    sut = sut.update_review(ReviewResult.Closed, remarks="Closed")

    assert sut.result == ReviewResult.Closed
    assert sut.remarks == "Closed"
