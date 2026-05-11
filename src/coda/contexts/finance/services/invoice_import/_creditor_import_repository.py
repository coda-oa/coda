"""Import-scoped creditor repository.

Prefetches existing creditors in one query, stages missing ones for bulk
creation via UnitOfWork, and resolves CreditorIds after flush.
"""

from coda.apps.import_repository import BulkImportRepository
from coda.apps.invoices.models import Creditor
from coda.domain.finance.invoice import CreditorId


class CreditorImportRepository(BulkImportRepository[Creditor, str, CreditorId]):
    model = Creditor
    lookup_field = "name"
    id_type = CreditorId
    lookup_type = str

    def create(self, value: str) -> Creditor:
        return Creditor(name=value)
