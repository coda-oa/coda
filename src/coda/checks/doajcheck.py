from collections.abc import Callable
from typing import Any, Protocol

from coda.checks.checklist import CheckFailed, CheckResult, CheckSuccessful
from coda.doaj import DoajListedJournal
from coda.fundingrequest import FundingRequest, TPublication
from coda.issn import Issn
from coda.publication import JournalId, Publication


class DoajApi(Protocol):
    def find_journal(self, issn: Issn) -> DoajListedJournal | None:
        raise NotImplementedError


IssnProvider = Callable[[JournalId], Issn]


class DoajCheck:
    name = "Check DOAJ listing"
    params: dict[str, Any] = {}

    def __init__(self, doaj_api: DoajApi, get_issn: IssnProvider) -> None:
        self.api = doaj_api
        self.get_issn = get_issn

    @property
    def description(self) -> str:
        return "Journal must be listed in DOAJ"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        assert isinstance(fundingrequest.publication, Publication)
        issn = self.get_issn(fundingrequest.publication.journal)
        journal = self.api.find_journal(issn)

        if journal is None:
            return CheckFailed("Journal not listed in DOAJ")

        return CheckSuccessful(journal)
