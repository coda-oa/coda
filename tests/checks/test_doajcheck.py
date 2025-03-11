from dataclasses import dataclass, field

import pytest

from coda import doaj
from coda.checks.checklist import CheckFailed, CheckSuccessful
from coda.checks.doajcheck import DoajCheck
from coda.doaj import DoajListedJournal
from coda.issn import Issn
from coda.publication.publication import JournalId
from tests import domainfactory
from tests.test_doaj import DOAJ_LISTED_ISSN, EXPECTED_JOURNAL


def issn_provider(journal_id: JournalId) -> Issn:
    return DOAJ_LISTED_ISSN


def doaj_journal() -> DoajListedJournal:
    return EXPECTED_JOURNAL


def doaj_journal_dict() -> dict[str, str | int]:
    return {
        "title": "Materials Today Quantum",
        "publisher": "Elsevier",
        "issn": "2950-2578",
        "apc": "2770.00 USD",
        "doaj_url": "https://doaj.org/toc/2950-2578",
    }


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

    assert result == CheckSuccessful(data=doaj_journal_dict())


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

    assert result == CheckSuccessful(data=doaj_journal_dict())
