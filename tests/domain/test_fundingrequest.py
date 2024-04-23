import pytest

from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    FundingRequestLocked,
    ProcessingStatus,
)
from coda.author import AuthorId
from coda.money import Currency, Money
from coda.publication import JournalId, Publication, PublicationId
from coda.string import NonEmptyStr


def make_sut() -> FundingRequest:
    sut = FundingRequest(
        id=FundingRequestId(8),
        publication=Publication(
            id=PublicationId(8),
            title="Publication Title",
            journal=JournalId(3),
        ),
        submitter=AuthorId(1),
        estimated_cost=Money(100, Currency.EUR),
        external_funding=ExternalFunding(
            organization=FundingOrganizationId(1),
            project_id=NonEmptyStr("123"),
            project_name="Project Name",
        ),
    )

    return sut


def test__new_fundingrequest__processing_status_is_open() -> None:
    sut = make_sut()

    assert sut.status() == ProcessingStatus.Open


def test__open_fundingrequest__approve__changes_status_to_approved() -> None:
    sut = make_sut()

    status = sut.approve()

    assert status == ProcessingStatus.Approved
    assert sut.status() == ProcessingStatus.Approved


def test__open_fundingrequest__reject__changes_status_to_rejected() -> None:
    sut = make_sut()

    status = sut.reject()

    assert status == ProcessingStatus.Rejected
    assert sut.status() == ProcessingStatus.Rejected


def test__approved_fundingrequest__reject__cannot_change_status() -> None:
    sut = make_sut()
    sut.approve()

    with pytest.raises(ValueError):
        sut.reject()

    assert sut.status() == ProcessingStatus.Approved


def test__rejected_fundingrequest__approve__cannot_change_status() -> None:
    sut = make_sut()
    sut.reject()

    with pytest.raises(ValueError):
        sut.approve()

    assert sut.status() == ProcessingStatus.Rejected


def test__rejected_fundingrequest__open__changes_status_to_open() -> None:
    sut = make_sut()
    sut.reject()

    status = sut.open()

    assert status == ProcessingStatus.Open
    assert sut.status() == ProcessingStatus.Open


def test__approved_fundingrequest__changing_publication_journal__raises_error() -> None:
    sut = make_sut()
    sut.approve()
    old_journal = sut.publication.journal

    with pytest.raises(FundingRequestLocked):
        sut.publication.journal = JournalId(4)

    assert sut.publication.journal == old_journal


def test__rejected_fundingrequest__changing_publication_journal__raises_error() -> None:
    sut = make_sut()
    sut.reject()
    old_journal = sut.publication.journal

    with pytest.raises(FundingRequestLocked):
        sut.publication.journal = JournalId(4)

    assert sut.publication.journal == old_journal


def test__open_fundingrequest__changing_publication_journal__changes_journal() -> None:
    sut = make_sut()

    sut.publication.journal = JournalId(4)

    assert sut.publication.journal == JournalId(4)


def test__approved_then_reopened_fundingrequest__changing_publication_journal__changes_journal() -> (
    None
):
    sut = make_sut()
    sut.approve()
    sut.open()

    sut.publication.journal = JournalId(4)

    assert sut.publication.journal == JournalId(4)


def test__open_fundingrequest__open__does_not_change_status() -> None:
    sut = make_sut()
    sut.open()

    status = sut.open()

    assert status == ProcessingStatus.Open
    assert sut.status() == ProcessingStatus.Open


def test__finished_fundingrequest__is_open__is_false() -> None:
    sut = make_sut()
    sut.approve()
    assert not sut.is_open()

    sut = make_sut()
    sut.reject()
    assert not sut.is_open()
