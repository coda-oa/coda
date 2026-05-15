from collections.abc import Collection, Generator, Iterable
from typing import Final, cast

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
    MESSAGE = "Setting this parent would create a cycle in the institution hierarchy."

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


def _walk_ancestor_ids(
    start_id: int,
    parent_lookup: dict[int, int | None] | None = None,
) -> Generator[int]:
    """Yield each ancestor pk walking up the parent chain from start_id.

    Uses parent_lookup for in-memory resolution where available,
    falling back to DB queries for ids not in the lookup.
    Raises HierarchyDepthExceeded if the chain exceeds the limit.
    """
    depth = 0
    current_id: int | None = start_id
    while current_id is not None:
        depth += 1
        if depth > INSTITUTION_HIERARCHY_LIMIT:
            raise HierarchyDepthExceeded()
        yield current_id
        if parent_lookup is not None and current_id in parent_lookup:
            current_id = parent_lookup[current_id]
        else:
            inst = Institution.objects.only("parent_id").get(pk=current_id)
            current_id = inst.parent_id


def _check_batch_cycles(instances: list["Institution"]) -> None:
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

        for ancestor_id in _walk_ancestor_ids(inst.parent_id, parent_lookup):
            if ancestor_id == inst.pk:
                raise HierarchyContainsCycle()


class InstitutionQuerySet(models.QuerySet["Institution"]):
    def archived_only(self) -> "InstitutionQuerySet":
        return self.filter(archived_at__isnull=False)

    def all_with_archived(self) -> "InstitutionQuerySet":
        return self

    def bulk_create(
        self,
        objs: Iterable["Institution"],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Collection[str] | None = None,
        unique_fields: Collection[str] | None = None,
    ) -> list["Institution"]:
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
        objs: Iterable["Institution"],
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


AllInstitutionManager = models.Manager.from_queryset(InstitutionQuerySet)


class Institution(models.Model):
    name = models.CharField(max_length=255)
    internal_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        default=None,
        help_text="Stable identifier for import/export matching",
    )
    virtual = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )

    archived_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="When this institution was archived"
    )

    objects = InstitutionManager()
    all_objects = AllInstitutionManager()

    def clean(self) -> None:
        super().clean()
        if self._contains_cycle():
            raise ValidationError(HierarchyContainsCycle.MESSAGE)

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        if self._contains_cycle():
            raise HierarchyContainsCycle()
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

    def is_descendant_of(self, other: "Institution") -> bool:
        if self.pk is None or other.pk is None or self.pk == other.pk:
            return False

        if self.parent_id is None:
            return False

        return other.pk in _walk_ancestor_ids(self.parent_id)

    def set_parent(self, parent: "Institution | None") -> None:
        self.parent = parent

    def walk(self) -> Generator["Institution"]:
        visited: set[int] = set()
        stack: list["Institution"] = [self]
        while stack:
            current = stack.pop()
            if current.pk in visited:
                raise ValueError("Cycle detected during walk — hierarchy is corrupted")
            visited.add(current.pk)
            yield current
            for child in current.children.all():
                stack.append(child)

    def archive(self) -> None:
        self.archived_at = timezone.now()
        self.save()

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
