"""Import-scoped creditor repository.

Prefetches existing creditors in one query, stages missing ones for bulk
creation via UnitOfWork, and resolves CreditorIds after flush.
"""

from coda.apps.invoices.models import Creditor
from coda.domain.finance.invoice import CreditorId
from coda.uow import UnitOfWork


class CreditorImportRepository:
    def __init__(self) -> None:
        self._cache: dict[str, CreditorId] = {}

    def prefetch(self, names: set[str]) -> None:
        """Bulk load existing creditors into the cache (one query)."""
        for creditor in Creditor.objects.filter(name__in=names):
            self._cache[creditor.name] = CreditorId(creditor.pk)

    def get_or_create(self, uow: UnitOfWork, name: str) -> CreditorId:
        """Return a CreditorId for name, staging a new Creditor if not found."""
        if name in self._cache:
            return self._cache[name]
        creditor_id = CreditorId()
        uow.register(Creditor(name=name), creditor_id)
        self._cache[name] = creditor_id
        return creditor_id

    def flush(self, uow: UnitOfWork) -> None:
        """Bulk create staged creditors and resolve their CreditorIds."""
        staged = uow.get_staged(Creditor)
        if not staged:
            return
        created = Creditor.objects.bulk_create([creditor for creditor, _ in staged])
        for model, (_, creditor_id) in zip(created, staged):
            creditor_id.resolve(model.pk)
