import pytest
from coda import doaj
from coda.doaj import DoajListedJournal, HasApc
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money

# Data taken from https://doaj.org/toc/2950-2578
# at March 4th, 2025

DOAJ_LISTED_ISSN = Issn("2950-2578")
EXPECTED_JOURNAL = DoajListedJournal(
    title="Materials Today Quantum",
    publisher="Elsevier",
    issn=DOAJ_LISTED_ISSN,
    apc=HasApc(price=Money(2770, Currency.USD)),
    doaj_url="https://doaj.org/toc/2950-2578",
)


@pytest.mark.integration
def test__doaj__searching_for_listed_issn__returns_journal() -> None:
    assert doaj.find_journal(DOAJ_LISTED_ISSN) == EXPECTED_JOURNAL
