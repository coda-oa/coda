import datetime
import pytest

from coda.apps.blocklist.models import BlockList
from coda.apps.fundingrequests import repository
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.checks.blockcheck import BlockCheck
from coda.checks.checklist import CheckFailed, CheckSuccessful, CheckWarning
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest
from coda.domain.publication import JournalId, Monograph, Publication
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__fundingrequest_for_article_in_blocked_journal__fails_blockcheck() -> None:
    journal = blocked_journal()
    fundingrequest = fundingrequest_for_article(journal)

    sut = BlockCheck()
    result = sut(fundingrequest)

    assert isinstance(result, CheckFailed)


@pytest.mark.django_db
def test__fundingrequest_for_article_for_blocked_publisher__fails_blockcheck() -> None:
    journal = journal_of_blocked_publisher()
    fundingrequest = fundingrequest_for_article(journal)

    sut = BlockCheck()
    result = sut(fundingrequest)

    assert isinstance(result, CheckFailed)


@pytest.mark.django_db
def test__fundingrequest_for_article_in_unblocked_journal__passes_blockcheck() -> None:
    journal = modelfactory.journal()
    fundingrequest = fundingrequest_for_article(journal)

    sut = BlockCheck()
    result = sut(fundingrequest)

    assert isinstance(result, CheckSuccessful)


@pytest.mark.django_db
def test__fundingrequest_for_monograph_of_blocked_publisher__fails_blockcheck() -> None:
    publisher = blocked_publisher()
    fundingrequest = fundingrequest_for_monograph(publisher)

    sut = BlockCheck()
    result = sut(fundingrequest)

    assert isinstance(result, CheckFailed)


@pytest.mark.django_db
def test__fundingreuqest_for_monograph_of_unblocked_publisher__passes_blockcheck() -> None:
    publisher = modelfactory.publisher()
    fundingrequest = fundingrequest_for_monograph(publisher)

    sut = BlockCheck()
    result = sut(fundingrequest)

    assert isinstance(result, CheckSuccessful)


@pytest.mark.django_db
def test__fundingrequest_for_article_in_blocked_journal_in_need_of_review__passes_blockcheck_with_warning() -> (
    None
):
    over_six_months_ago = datetime.datetime.now() - datetime.timedelta(days=181)
    journal = blocked_journal(blocked_at=over_six_months_ago)
    fundingrequest = fundingrequest_for_article(journal)

    sut = BlockCheck()
    result = sut(fundingrequest)

    assert isinstance(result, CheckWarning)


def fundingrequest_for_article(journal: Journal) -> FundingRequest[Publication]:
    article = domainfactory.publication(journal=JournalId(journal.id))
    fundingrequest = FundingRequest.new(article, domainfactory.payment())
    fundingrequest.id = repository.create(fundingrequest)
    return fundingrequest


def blocked_journal(blocked_at: datetime.datetime | None = None) -> Journal:
    journal = modelfactory.journal()
    blocklist = BlockList.objects.get()
    blocklist.block_journal(journal, reason="PREDATORY", now=blocked_at)
    return journal


def journal_of_blocked_publisher() -> Journal:
    journal = modelfactory.journal()
    blocklist = BlockList.objects.get()
    blocklist.block_publisher(journal.publisher)
    return journal


def fundingrequest_for_monograph(publisher: Publisher) -> FundingRequest[Monograph]:
    monograph = domainfactory.monograph(publisher=PublisherId(publisher.id))
    fundingrequest = FundingRequest.new(monograph, domainfactory.payment())
    fundingrequest.id = repository.create(fundingrequest)
    return fundingrequest


def blocked_publisher() -> Publisher:
    publisher = modelfactory.publisher()
    blocklist = BlockList.objects.get()
    blocklist.block_publisher(publisher)
    return publisher
