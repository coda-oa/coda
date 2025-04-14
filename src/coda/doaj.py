from dataclasses import dataclass
import json
from typing import Any, Final

import httpx

from coda.domain.issn import Issn
from coda.domain.money import Money
from coda.domain.money._currency import Currency


@dataclass(frozen=True, slots=True)
class HasApc:
    price: Money


@dataclass(frozen=True, slots=True)
class NoApc_:
    pass


NoApc: Final = NoApc_()
Apc = HasApc | NoApc_


@dataclass(frozen=True, slots=True)
class DoajListedJournal:
    title: str
    publisher: str
    issn: Issn
    apc: Apc
    doaj_url: str = ""


DoajJournalUrlBase: Final = "https://doaj.org/toc/{issn}"
DoajJournalSearchUrl: Final = "https://doaj.org/api/search/journals/issn:{issn}"


def find_journal(issn: Issn) -> DoajListedJournal | None:
    url = DoajJournalSearchUrl.format(issn=issn)
    response = httpx.get(url)
    data = _try_parse(response)

    if not data:
        return None

    journal_entry = data[0].get("bibjson", {})
    apc_data = journal_entry.get("apc", {}).get("max")
    apc: Apc = NoApc
    if apc_data:
        first_apc = apc_data[0]
        apc = HasApc(
            price=Money(first_apc.get("price"), Currency.from_code(first_apc.get("currency")))
        )

    return DoajListedJournal(
        title=journal_entry.get("title"),
        publisher=journal_entry.get("publisher", {}).get("name"),
        issn=Issn(journal_entry.get("eissn")),
        apc=apc,
        doaj_url=DoajJournalUrlBase.format(issn=issn),
    )


def _try_parse(response: httpx.Response) -> Any:
    try:
        data = response.json().get("results", [])
    except json.decoder.JSONDecodeError:
        data = None

    return data
