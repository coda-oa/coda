"""Generic lookup table for bulk import operations.

Provides an in-memory cache that maps a lookup key to both a Django model
instance and its EntityId. Used as the building block for import repositories
that need to prefetch existing entities and stage new ones for bulk creation.

Two levels of API:

1. ``BulkImportRepository`` (see ``coda.apps.import_repository``) — for the
   common single-model case; uses ``Lookup`` internally.

2. ``Lookup`` directly — for complex repositories that compose multiple lookups
   (e.g. a funding source repository that maintains separate caches for budgets
   and institutions).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from django.db.models import Model

from coda.entityid import EntityId


@dataclass(frozen=True, slots=True, kw_only=True)
class LookupConfig[TModel: Model, TId: EntityId, TLookup]:
    model_type: type[TModel]
    id_type: type[TId]
    lookup_type: type[TLookup]
    lookup_field: str


class Lookup[TModel: Model, TId: EntityId, TLookup]:
    """In-memory cache mapping a lookup key to a model instance and its EntityId.

    Typical lifecycle::

        lookup = Lookup(Institution, "name", InstitutionId)
        lookup.initialize_lookup({"MIT", "Harvard"})   # one DB query

        if "MIT" in lookup:
            institution_id = lookup.get_id("MIT")
        else:
            id_ = InstitutionId()
            lookup.put("MIT", Institution(name="MIT"), id_)

    After bulk_create, resolve EntityIds in-place::

        for model, (_, entity_id) in zip(created, staged):
            entity_id.resolve(model.pk)
    """

    def __init__(self, config: LookupConfig[TModel, TId, TLookup]) -> None:
        self._model = config.model_type
        self._id_type = config.id_type
        self._lookup_field = config.lookup_field
        self._lookup: dict[TLookup, TModel] = {}
        self._id_lookup: dict[TLookup, TId] = {}
        self._ = config.lookup_type

    def initialize_lookup(self, lookup_values: Iterable[TLookup]) -> None:
        """Bulk load existing entities from the database (one query)."""
        filtered = self._model.objects.filter(  # type: ignore[attr-defined]
            **{f"{self._lookup_field}__in": lookup_values}
        )
        for entity in filtered:
            key = getattr(entity, self._lookup_field)
            self._lookup[key] = entity
            self._id_lookup[key] = self._id_type(entity.pk)

    def put(self, lookup_value: TLookup, model: TModel, entity_id: TId | None = None) -> None:
        """Stage a model instance under the given lookup key."""
        self._lookup[lookup_value] = model
        if entity_id is not None:
            self._id_lookup[lookup_value] = entity_id

    def get(self, lookup_value: TLookup) -> TModel:
        """Return the model instance for a lookup key."""
        return self._lookup[lookup_value]

    def get_id(self, lookup_value: TLookup) -> TId:
        """Return the EntityId for a lookup key."""
        return self._id_lookup[lookup_value]

    def __contains__(self, lookup_value: TLookup) -> bool:
        return lookup_value in self._lookup

    def __setitem__(self, lookup_value: TLookup, model: TModel) -> None:
        self.put(lookup_value, model)

    def __getitem__(self, lookup_value: TLookup) -> TModel:
        return self.get(lookup_value)
