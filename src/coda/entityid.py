class EntityId:
    """An entity identifier that may not yet be assigned a database PK.

    Subclass per entity type::

        class JournalId(EntityId): pass
        class FundingRequestId(EntityId): pass

    Construct unresolved (before DB write)::

        journal_id = JournalId()

    Construct from a known PK (existing entity)::

        journal_id = JournalId(pk)

    Resolved in-place by the repository after flush. All objects holding
    the same instance see the PK automatically.
    """

    def __init__(self, pk: int | None = None) -> None:
        self._pk = pk

    def resolve(self, pk: int) -> None:
        """Called by the repository after the entity is persisted."""
        self._pk = pk

    @property
    def pk(self) -> int:
        if self._pk is None:
            raise UnresolvedEntityId(self)
        return self._pk

    @property
    def resolved(self) -> bool:
        return self._pk is not None

    def __int__(self) -> int:
        return self.pk

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EntityId):
            return self._pk == other._pk
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._pk)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(pk={self._pk!r})"

    def __bool__(self) -> bool:
        return self._pk is not None

    def __str__(self) -> str:
        return str(self._pk)


class UnresolvedEntityId(Exception):
    def __init__(self, entity_id: EntityId) -> None:
        super().__init__(
            f"{entity_id!r} has not been resolved yet. "
            f"Ensure the owning repository is flushed before accessing .pk."
        )
        self.entity_id = entity_id
