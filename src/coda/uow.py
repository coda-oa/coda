"""Generic Unit of Work.

Collects domain objects staged for creation, then flushes them in bulk
via repositories. Flush order is determined by the order repositories
are passed to the UnitOfWork constructor.

Two registration styles are supported:

1. Domain models that own their EntityId (assigned in the constructor or
   factory method)::

       fr = FundingRequest.new(...)   # fr.id is a FundingRequestId()
       uow.register(fr)               # UoW reads fr.id directly

2. Objects without a domain model (e.g. bare Django models used as-is)
   where the EntityId is created externally by the repository::

       journal_id = JournalId()
       uow.register(journal_model, journal_id)

Flush order = repository constructor order::

    with UnitOfWork(JournalRepository(), FundingRequestRepository()) as uow:
        journal_id = journal_repo.get_or_create(uow, eissn, ...)
        fr = FundingRequest.new(publication=Publication(journal=journal_id))
        fr_repo.create(uow, fr)
    # journals flushed first, FRs second, all in one transaction

Mutating a staged entity before flush::

    journal_id = journal_repo.get_or_create(uow, eissn, ...)
    journal = uow.get(journal_id)
    journal.title = "Updated Title"
    # same object reference — mutation visible at flush automatically
"""

from __future__ import annotations

from typing import Protocol, TypeVar, overload, runtime_checkable

from django.db import transaction

from coda.entityid import EntityId

DomainT = TypeVar("DomainT")


@runtime_checkable
class HasEntityId(Protocol):
    """Domain models that own their EntityId implement this protocol.

    Declared as a read-only property so that subclasses of EntityId
    (e.g. InvoiceId, FundingRequestId) satisfy the protocol covariantly.
    Mutable attribute declarations are invariant in mypy, which would
    reject ``id: InvoiceId`` as not matching ``id: EntityId``.
    """

    @property
    def id(self) -> EntityId: ...


class Repository(Protocol):
    """Protocol that repositories must implement to participate in a UnitOfWork."""

    def flush(self, uow: UnitOfWork) -> None:
        """Persist all staged entities of this repository's type and resolve their EntityIds."""
        ...


class UnitOfWork:
    """Coordinates bulk persistence across repositories in a single transaction.

    Repositories are flushed in the order they are passed to the constructor,
    which determines FK dependency order. The caller is responsible for passing
    repositories in the correct order.

    Entities are staged via ``register()``, retrieved for mutation via ``get()``,
    and persisted on ``flush()`` / context manager exit.
    """

    def __init__(self, *repositories: Repository) -> None:
        self._repositories = repositories
        # Keyed by id(entity_id) — object identity — so that:
        # - lookup is O(1)
        # - unresolved EntityIds (all pk=None) don't collide
        # - EntityId.__eq__ stays value-based (JournalId(1) == JournalId(1))
        self._staged: dict[int, tuple[object, EntityId]] = {}

    @overload
    def register(self, entity: HasEntityId) -> None:
        """Stage a domain model that owns its EntityId.

        The EntityId is read from ``entity.id`` directly. Use this for domain
        models whose factory methods assign an unresolved EntityId on construction::

            fr = FundingRequest.new(...)  # fr.id = FundingRequestId()
            uow.register(fr)
        """
        ...

    @overload
    def register(self, entity: object, entity_id: EntityId) -> None:
        """Stage an object with an externally created EntityId.

        Use this for objects without a domain model (e.g. bare Django models)
        where the repository creates the EntityId::

            journal_id = JournalId()
            uow.register(journal_model, journal_id)
        """
        ...

    def register(self, entity: object, entity_id: EntityId | None = None) -> None:
        if entity_id is None:
            if not isinstance(entity, HasEntityId):
                raise ValueError(
                    f"{type(entity).__name__} does not have an 'id: EntityId' attribute. "
                    f"Pass the EntityId explicitly: uow.register(entity, entity_id)."
                )
            entity_id = entity.id
        self._staged[id(entity_id)] = (entity, entity_id)

    def get(self, entity_id: EntityId) -> object:
        """Return a staged domain object by its EntityId (pre-flush only).

        Use this to mutate a staged entity before flush. Because the UoW holds
        the same object reference, mutations are visible at flush automatically.

        Raises:
            KeyError: if the entity_id is not found among staged entities.
        """
        entry = self._staged.get(id(entity_id))
        if entry is None:
            raise KeyError(
                f"No staged entity for {entity_id!r}. Entity may have already been flushed."
            )
        return entry[0]

    def get_staged(self, domain_type: type[DomainT]) -> list[tuple[DomainT, EntityId]]:
        """Return all staged entities of a given domain type.

        Called by repositories during flush to retrieve their batch.
        """
        return [
            (entity, entity_id)
            for entity, entity_id in self._staged.values()
            if isinstance(entity, domain_type)
        ]

    @transaction.atomic
    def flush(self) -> None:
        """Persist all staged entities via repositories, in constructor order.

        Each repository pulls its own entities from the UoW via get_staged(),
        performs bulk persistence, and resolves EntityIds with real PKs.
        All writes happen inside a single transaction.
        """
        for repository in self._repositories:
            repository.flush(self)
        self._staged.clear()

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if exc_type is None:
            self.flush()
