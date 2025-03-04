from collections.abc import Callable
from typing import Protocol

from coda.checks.checklist import Check, CheckFailed, CheckResult, CheckSuccessful
from coda.doaj import DoajListedJournal
from coda.fundingrequest import FundingRequest
from coda.issn import Issn
from coda.publication.publication import JournalId, Publication


class DoajApi(Protocol):
    def find_journal(self, issn: Issn) -> DoajListedJournal | None:
        raise NotImplementedError


IssnProvider = Callable[[JournalId], Issn]


class DoajCheck(Check[Publication]):
    name = "Check DOAJ listing"

    def __init__(self, doaj_api: DoajApi, get_issn: IssnProvider) -> None:
        self.api = doaj_api
        self.get_issn = get_issn

    @property
    def description(self) -> str:
        return "Journal must be listed in DOAJ"

    def __call__(self, fundingrequest: FundingRequest[Publication]) -> CheckResult:
        issn = self.get_issn(fundingrequest.publication.journal)
        journal = self.api.find_journal(issn)

        if journal is None:
            return CheckFailed("Journal not listed in DOAJ")

        return CheckSuccessful(journal)
