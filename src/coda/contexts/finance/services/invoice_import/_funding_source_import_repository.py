"""Import-scoped funding source repository.

Handles two use cases:

1. Single funding source per position (``get_or_create``):
   Returns a ``FundingSourceId`` for use in ``position.assign_remaining(Budget(id, name))``.

2. Split funding assignments (``get_or_create_for_assignment``):
   Returns a full ``FundingSource`` domain object (``Budget`` or ``SplitSource``)
   for use in ``PartialAssignment(funding_source, amount)``.

In both cases, new ``FundingSource`` rows are staged via UnitOfWork and bulk-created
at flush. The ``FundingSourceId`` instances are resolved in-place after bulk_create,
so all domain objects holding the same instance see the PK automatically.
"""

from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, SplitSource
from coda.domain.finance.funding_sources import FundingSource as FundingSourceDomain
from coda.domain.finance.invoice import FundingSourceId
from coda.lookup import Lookup, LookupConfig
from coda.uow import UnitOfWork


class FundingSourceImportRepository:
    def __init__(self) -> None:
        self._funding_sources = Lookup(
            LookupConfig(
                model_type=FundingSource,
                id_type=FundingSourceId,
                lookup_field="name",
                lookup_type=str,
            )
        )
        self._institutions = Lookup(
            LookupConfig(
                model_type=Institution,
                id_type=InstitutionId,
                lookup_field="name",
                lookup_type=str,
            )
        )
        self._domain_cache: dict[str, FundingSourceDomain] = {}

    def prefetch_funding_sources(self, names: set[str]) -> None:
        """Bulk load existing budget funding sources into the cache (one query)."""
        filtered = FundingSource.objects.filter(name__in=names, type="budget")
        for fs in filtered:
            self._funding_sources.put(fs.name, fs, FundingSourceId(fs.pk))

    def prefetch_institutions(self, names: set[str]) -> None:
        """Bulk load institution name → InstitutionId mappings (one query)."""
        self._institutions.initialize_lookup(names)

    def get_or_create(self, uow: UnitOfWork, name: str) -> FundingSourceDomain:
        """Return a Budget domain object for a funding source, staging if not found."""
        if name in self._funding_sources:
            return Budget(self._funding_sources.get_id(name), name)

        funding_source_id = FundingSourceId()
        uow.register(FundingSource(name=name), funding_source_id)
        self._funding_sources.put(name, FundingSource(name=name), funding_source_id)
        return Budget(funding_source_id, name)

    def get_or_create_for_assignment(
        self,
        uow: UnitOfWork,
        type_: str,
        name: str,
    ) -> FundingSourceDomain:
        """Return a FundingSource domain object for a split assignment, staging if not found.

        Args:
            uow: Unit of work for staging new FundingSource rows.
            type_: ``"budget"`` or ``"institution"``.
            name: Budget name or institution name.

        Returns:
            A ``Budget`` or ``SplitSource`` domain object whose ``id`` will be
            resolved after flush.

        Raises:
            KeyError: if ``type_`` is ``"institution"`` and the institution was not
                found during ``prefetch_institutions``.
        """
        if name in self._domain_cache:
            return self._domain_cache[name]

        if type_ == "institution":
            institution_id = self._institutions.get_id(name)
            funding_source_id = FundingSourceId()
            uow.register(
                FundingSource(type="institution", name=name, institution_id=institution_id.pk),
                funding_source_id,
            )
            domain_obj: FundingSourceDomain = SplitSource(
                id=funding_source_id,
                institution=institution_id,
                institution_name=name,
            )
        else:
            funding_source_id = FundingSourceId()
            uow.register(FundingSource(name=name), funding_source_id)
            domain_obj = Budget(id=funding_source_id, name=name)

        self._domain_cache[name] = domain_obj
        return domain_obj

    def flush(self, uow: UnitOfWork) -> None:
        """Bulk create staged funding sources and resolve their FundingSourceIds."""
        staged = uow.get_staged(FundingSource)
        if not staged:
            return
        created = FundingSource.objects.bulk_create([fs for fs, _ in staged])
        for model, (_, funding_source_id) in zip(created, staged):
            funding_source_id.resolve(model.pk)
