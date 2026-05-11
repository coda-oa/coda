"""Generic base class for bulk import repositories.

Provides the common prefetch → get-or-create → flush lifecycle for import
operations that stage bare Django models via a UnitOfWork.

Usage — subclass and declare three class attributes plus ``create``::

    class CreditorImportRepository(BulkImportRepository[Creditor, str, CreditorId]):
        model = Creditor
        lookup_field = "name"
        id_type = CreditorId

        def create(self, name: str) -> Creditor:
            return Creditor(name=name)

The default ``flush`` handles the common case: ``bulk_create`` the staged
Django models and resolve each EntityId in-place. Override ``flush`` when
the staged objects are domain models that require mapping or relationship
synchronisation before persistence (see ``coda.apps.invoices.repository``
for an example of that pattern).

For repositories that cannot fit the single-model template (e.g. a funding
source repository that maintains separate caches for budgets and institutions),
use ``coda.lookup.Lookup`` directly and compose multiple instances.
"""

from collections.abc import Iterable

from django.db.models import Model

from coda.entityid import EntityId
from coda.lookup import Lookup, LookupConfig
from coda.uow import UnitOfWork


class BulkImportRepository[TModel: Model, TLookup, TId: EntityId]:
    """Template-method base class for single-model bulk import repositories.

    Subclasses must declare:

    - ``model``: the Django model class to persist
    - ``lookup_field``: the field used to identify existing instances
    - ``id_type``: the ``EntityId`` subclass for this model

    And implement:

    - ``create(value)``: construct an unsaved model instance from a lookup value

    Optionally override:

    - ``flush(uow)``: when staged objects are domain models that need mapping
      or relationship synchronisation before ``bulk_create``
    """

    model: type[TModel]
    lookup_field: str
    id_type: type[TId]
    lookup_type: type[TLookup]

    def __init__(self) -> None:
        self._lookup = Lookup(
            LookupConfig(
                model_type=self.model,
                id_type=self.id_type,
                lookup_field=self.lookup_field,
                lookup_type=self.lookup_type,
            )
        )

    def create(self, value: TLookup) -> TModel:
        """Construct an unsaved model instance for a new lookup value.

        Subclasses must override this method.
        """
        raise NotImplementedError

    def prefetch(self, values: Iterable[TLookup]) -> None:
        """Bulk load existing entities into the cache (one query)."""
        self._lookup.initialize_lookup(values)

    def get_or_create(self, uow: UnitOfWork, value: TLookup) -> TId:
        """Return an EntityId for value, staging a new model instance if not found."""
        if value in self._lookup:
            return self._lookup.get_id(value)

        entity_id = self.id_type()
        model = self.create(value)
        uow.register(model, entity_id)
        self._lookup.put(value, model, entity_id)
        return entity_id

    def flush(self, uow: UnitOfWork) -> None:
        """Bulk create staged models and resolve their EntityIds in-place.

        Override this method when staged objects are domain models that require
        mapping or relationship synchronisation before persistence.
        """
        staged = uow.get_staged(self.model)
        if not staged:
            return
        created = self.model.objects.bulk_create([m for m, _ in staged])  # type: ignore[attr-defined]
        for model, (_, entity_id) in zip(created, staged):
            entity_id.resolve(model.pk)
