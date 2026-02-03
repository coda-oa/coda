from collections.abc import Callable
from typing import Any, Protocol

from typing import TypeIs

from coda import doaj
from coda.apps.journals import services
from coda.checks.checklist import CheckFailed, CheckResult, CheckSuccessful
from coda.domain.fundingrequest import FundingRequest, TPublication
from coda.domain.issn import Issn
from coda.domain.publication import JournalId, Publication


class DoajApi(Protocol):
    def find_journal(self, issn: Issn) -> doaj.DoajListedJournal | None:
        raise NotImplementedError


IssnProvider = Callable[[JournalId], Issn]


class DoajCheck:
    params: dict[str, Any] = {}

    def __init__(
        self, doaj_api: DoajApi = doaj, get_issn: IssnProvider = services.eissn_for
    ) -> None:
        self.api = doaj_api
        self.get_issn = get_issn

    @property
    def name(self) -> str:
        return "DOAJ Check"

    @property
    def description(self) -> str:
        return "Journal must be listed in DOAJ"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        assert isinstance(fundingrequest.publication, Publication)
        issn = self.get_issn(fundingrequest.publication.journal)
        journal = self.api.find_journal(issn)

        if journal is None:
            return CheckFailed("Journal not listed in DOAJ")

        return CheckSuccessful(message=self._format_doaj_url(journal), data=self._to_dict(journal))

    def _to_dict(self, doaj_journal: doaj.DoajListedJournal) -> dict[str, str | int]:
        return {"APC": self._format_apc_price(doaj_journal)}

    def _format_doaj_url(self, doaj_journal: doaj.DoajListedJournal) -> str:
        return f'<a href="{doaj_journal.doaj_url}">{doaj_journal.doaj_url}</a>'

    def _format_apc_price(self, doaj_journal: doaj.DoajListedJournal) -> str:
        apc = doaj_journal.apc
        if not self._has_apc(apc):
            return "No APC"

        return f"{apc.price.amount} {apc.price.currency.code}"

    def _has_apc(self, apc: doaj.Apc) -> TypeIs[doaj.HasApc]:
        return apc is not doaj.NoApc

    def __str__(self) -> str:
        return self.name
