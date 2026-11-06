from dataclasses import replace

import pytest

from coda import doaj
from coda.doaj import DoajListedJournal, HasApc
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money

# Data taken from https://doaj.org/toc/1932-6203
# The APC price changes regularly, so only its occurrence is asserted,
# never the exact amount.

DOAJ_LISTED_ISSN = Issn("1932-6203")
EXPECTED_JOURNAL = DoajListedJournal(
    title="PLoS ONE",
    publisher="Public Library of Science (PLoS)",
    issn=DOAJ_LISTED_ISSN,
    apc=HasApc(price=Money(0, Currency.USD)),
    doaj_url="https://doaj.org/toc/1932-6203",
)


@pytest.mark.integration
def test__doaj__searching_for_listed_issn__returns_journal() -> None:
    journal = doaj.find_journal(DOAJ_LISTED_ISSN)

    assert journal is not None
    assert journal == replace(EXPECTED_JOURNAL, apc=journal.apc)
    assert isinstance(journal.apc, HasApc)
    assert journal.apc.price.currency == Currency.USD
    assert journal.apc.price.amount > 0
