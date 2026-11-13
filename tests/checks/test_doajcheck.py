from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from coda import doaj
from coda.checks.checklist import CheckFailed, CheckSuccessful
from coda.checks.doajcheck import DoajCheck
from coda.doaj import DoajListedJournal, HasApc
from coda.domain.issn import Issn
from coda.domain.publication.publication import JournalId
from tests import domainfactory
from tests.test_doaj import DOAJ_LISTED_ISSN, EXPECTED_JOURNAL


def issn_provider(journal_id: JournalId) -> Issn:
    return DOAJ_LISTED_ISSN


def doaj_journal() -> DoajListedJournal:
    return EXPECTED_JOURNAL


def doaj_journal_dict() -> dict[str, str | int]:
    apc = doaj_journal().apc
    assert isinstance(apc, HasApc)
    return {"APC": f"{apc.price.amount} {apc.price.currency.code}"}


def doaj_url() -> str:
    return f'<a href="{doaj_journal().doaj_url}">{doaj_journal().doaj_url}</a>'


@dataclass
class DoajApiStub:
    journals: list[DoajListedJournal] = field(default_factory=list)

    @classmethod
    def with_listings(cls, *journals: DoajListedJournal) -> "DoajApiStub":
        return cls(list(journals))

    def find_journal(self, issn: Issn) -> DoajListedJournal | None:
        return next((j for j in self.journals if j.issn == issn), None)


def test__doaj_check__listing_required__journal_in_doaj__is_successful() -> None:
    fundingrequest = domainfactory.fundingrequest()
    api_stub = DoajApiStub.with_listings(doaj_journal())
    check = DoajCheck(api_stub, issn_provider)

    result = check(fundingrequest)

    assert result == CheckSuccessful(message=doaj_url(), data=doaj_journal_dict())


def test__doaj_check__listing_required__journal_not_in_doaj__fails() -> None:
    fundingrequest = domainfactory.fundingrequest()
    check = DoajCheck(DoajApiStub(), issn_provider)

    result = check(fundingrequest)

    assert result == CheckFailed("Journal not listed in DOAJ")


@pytest.mark.integration
def test__doaj_check_with_real_api__journal_in_doaj__is_successful() -> None:
    fundingrequest = domainfactory.fundingrequest()
    check = DoajCheck(doaj, issn_provider)

    result = check(fundingrequest)

    assert isinstance(result, CheckSuccessful)
    assert result.message == doaj_url()
    apc = result.data["APC"]
    assert isinstance(apc, str)
    assert apc.endswith(" USD")
    assert Decimal(apc.rsplit(" ", 1)[0]) > 0
