from __future__ import annotations

import datetime
from collections.abc import Collection, Generator, Iterable
from typing import TYPE_CHECKING, Final, TypeIs, cast

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.base import ModelBase
from django.utils import timezone

INSTITUTION_HIERARCHY_LIMIT: Final[int] = 100


class HierarchyDepthExceeded(ValueError):
    def __init__(self) -> None:
        super().__init__(
            f"Institution hierarchy exceeds maximum depth of {INSTITUTION_HIERARCHY_LIMIT}"
        )


class HierarchyContainsCycle(ValueError):
    CORRUPTED_HIERARCHY_MESSAGE = "Cycle detected during walk — hierarchy is corrupted"
    SETTING_INVALID_PARENT_MESSAGE = (
        "Setting this parent would create a cycle in the institution hierarchy."
    )

    @classmethod
    def invalid_parent(cls) -> HierarchyContainsCycle:
        return cls(cls.SETTING_INVALID_PARENT_MESSAGE)

    @classmethod
    def corrupted_hierarchy(cls) -> HierarchyContainsCycle:
        return cls(cls.CORRUPTED_HIERARCHY_MESSAGE)


def _walk_ancestor_ids(
    start: Institution,
    parent_lookup: dict[int, int | None] | None = None,
) -> Generator[int]:
    """Yield each ancestor pk walking up the parent chain from start.

    Begins at start's parent (start itself is not yielded or counted).
    Resolution order for each hop:
    1. In-memory parent object if the FK is cached on the current instance
       (avoids DB queries for dirty/unsaved objects)
    2. Explicit parent_lookup dict (used by bulk operations for batch overrides)
    3. DB fetch as fallback

    Raises HierarchyDepthExceeded if the chain exceeds the limit.
    """
    depth = 0
    current_id: int | None = start.pk
    current_obj: Institution | None = start
    parent_lookup = parent_lookup or {}

    while current_id is not None:
        yield current_id

        depth += 1
        if depth > INSTITUTION_HIERARCHY_LIMIT:
            raise HierarchyDepthExceeded()

        if _parent_loaded_in_memory(current_obj):
            current_obj = current_obj._state.fields_cache["parent"]
            current_id = current_obj.pk if current_obj is not None else None
        elif current_id in parent_lookup:
            current_id = parent_lookup[current_id]
            current_obj = None
        else:
            current_obj = Institution.all_objects.only("parent_id").get(pk=current_id)
            current_id = current_obj.parent_id


def _parent_loaded_in_memory(current_obj: Institution | None) -> TypeIs[Institution]:
    return current_obj is not None and "parent" in current_obj._state.fields_cache


def _check_batch_cycles(instances: list[Institution]) -> None:
    """Check for cycles in a batch of instances being created/updated.

    Walks parent chains efficiently: checks batch parents first (in-memory),
    then falls back to DB queries for parents outside the batch.
    """
    parent_lookup: dict[int, int | None] = {
        inst.pk: inst.parent_id
        for inst in instances
        if inst.pk is not None and inst.parent_id is not None
    }

    for inst in instances:
        if inst.parent_id is None:
            continue

        visited = set()
        for ancestor_id in _walk_ancestor_ids(inst, parent_lookup):
            if ancestor_id in visited:
                raise HierarchyContainsCycle.invalid_parent()

            visited.add(ancestor_id)


class InstitutionQuerySet(models.QuerySet["Institution"]):
    def archived_only(self) -> InstitutionQuerySet:
        return self.filter(archived_at__isnull=False)

    def all_with_archived(self) -> InstitutionQuerySet:
        return self

    def bulk_create(
        self,
        objs: Iterable[Institution],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Collection[str] | None = None,
        unique_fields: Collection[str] | None = None,
    ) -> list[Institution]:
        instances = list(objs)
        _check_batch_cycles(instances)
        return super().bulk_create(
            instances,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )

    def bulk_update(
        self,
        objs: Iterable[Institution],
        fields: Iterable[str],
        batch_size: int | None = None,
    ) -> int:
        instances = list(objs)
        _check_batch_cycles(instances)
        return super().bulk_update(instances, fields, batch_size=batch_size)


class InstitutionManager(models.Manager["Institution"]):
    def get_queryset(self) -> InstitutionQuerySet:
        return InstitutionQuerySet(self.model, using=self._db).filter(archived_at__isnull=True)

    def archived_only(self) -> InstitutionQuerySet:
        return InstitutionQuerySet(self.model, using=self._db).archived_only()


AllInstitutionManager: type[models.Manager[Institution]] = models.Manager.from_queryset(
    InstitutionQuerySet
)


class Institution(models.Model):
    objects = InstitutionManager()
    all_objects = AllInstitutionManager()

    if TYPE_CHECKING:
        parent_id: int | None
        children: models.QuerySet[Institution]

    name = models.CharField(max_length=255)
    virtual = models.BooleanField(default=False)
    internal_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        default=None,
        help_text="Stable identifier for import/export matching",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this institution was archived",
    )

    def clean(self) -> None:
        super().clean()
        if self._contains_cycle():
            raise ValidationError(HierarchyContainsCycle.SETTING_INVALID_PARENT_MESSAGE)

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        if self._contains_cycle():
            raise HierarchyContainsCycle.invalid_parent()
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def _contains_cycle(self) -> bool:
        if self.parent_id is None or self.pk is None:
            return False
        if self.parent_id == self.pk:
            return True

        parent = cast(Institution, self.parent)
        return parent.is_descendant_of(self)

    def is_descendant_of(self, other: Institution) -> bool:
        if self.pk is None or other.pk is None or self.pk == other.pk:
            return False

        if self.parent_id is None:
            return False

        return other.pk in _walk_ancestor_ids(self)

    def set_parent(self, parent: Institution | None) -> None:
        self.parent = parent

    def walk(self) -> Generator[Institution]:
        """Yield this institution and all descendants (depth-first).

        Children are discovered via DB queries (Institution.all_objects), so this
        includes archived nodes but only sees persisted children. Unsaved in-memory
        children whose parent_id points to a node in the tree will be silently
        skipped — there is no general way to discover them from the parent side
        without a DB query or the caller providing them explicitly.
        """
        visited: set[int] = set()
        stack: list[Institution] = [self]
        while stack:
            current = stack.pop()
            if current.pk in visited:
                raise HierarchyContainsCycle.corrupted_hierarchy()
            visited.add(current.pk)
            yield current
            for child in Institution.all_objects.filter(parent=current):
                stack.append(child)

    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self, timestamp: datetime.datetime | None = None) -> None:
        timestamp = timestamp or timezone.now()
        nodes = list(self.walk())
        for node in nodes:
            node.archived_at = timestamp
            node.virtual = True
        Institution.all_objects.bulk_update(nodes, fields=["archived_at", "virtual"])

    def archive_with_replacement(
        self, replacement: Institution, timestamp: datetime.datetime | None = None
    ) -> None:
        if replacement.pk == self.pk or replacement.is_descendant_of(self):
            raise HierarchyContainsCycle.invalid_parent()

        self.children.update(parent=replacement)
        self.archive(timestamp)

    def restore_without_children(self, new_parent: Institution | None = None) -> None:
        self.archived_at = None
        self.virtual = False
        if new_parent is not None:
            self.set_parent(new_parent)
        self.save()

    def restore_with_children(self, new_parent: Institution | None = None) -> None:
        if new_parent is not None:
            self.set_parent(new_parent)

        nodes = list(self.walk())
        for node in nodes:
            if node.archived_at is None:
                continue
            node.archived_at = None
            node.virtual = False

        Institution.all_objects.bulk_update(nodes, fields=["archived_at", "virtual", "parent"])

    def __repr__(self) -> str:
        return f"Institution(id={self.pk}, name={self.name})"

    def __str__(self) -> str:
        return self.name


class InstitutionLinkType(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.name


class InstitutionLink(models.Model):
    type = models.ForeignKey(InstitutionLinkType, on_delete=models.CASCADE)
    value = models.TextField()
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="links")

    def __str__(self) -> str:
        return f"{self.type.name}: {self.value}"
