"""Import-scoped institution repository.

Prefetches existing institutions in one query (including soft-deleted, via
``all_objects``), stages missing ones for bulk creation via UnitOfWork, and
resolves InstitutionIds after flush.
"""

from collections.abc import Iterable

from coda.apps.import_repository import BulkImportRepository
from coda.apps.institutions.models import Institution
from coda.domain.author import InstitutionId
from coda.lookup import Lookup, LookupConfig


class InstitutionImportRepository(BulkImportRepository[Institution, str, InstitutionId]):
    model = Institution
    lookup_field = "name"
    id_type = InstitutionId

    def __init__(self) -> None:
        # Use all_objects for prefetch so soft-deleted institutions are included,
        # preventing duplicate creation. BulkImportRepository.__init__ would use
        # the default manager, so we initialise the Lookup manually here.
        self._lookup = Lookup(
            LookupConfig(
                model_type=Institution,
                id_type=InstitutionId,
                lookup_field="name",
                lookup_type=str,
            )
        )

    def prefetch(self, values: Iterable[str]) -> None:
        """Bulk load existing institutions into the cache (one query, includes soft-deleted)."""
        institutions = Institution.all_objects.filter(name__in=values).distinct().order_by("id")
        for institution in institutions:
            self._lookup.put(institution.name, institution, InstitutionId(institution.pk))

    def create(self, value: str) -> Institution:
        return Institution(name=value)
