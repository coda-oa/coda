from collections.abc import Collection, Generator, Iterable
from typing import cast
from uuid import uuid4, UUID

from django.db import models
from django.db.models.base import ModelBase
from django.utils import timezone


def _compute_path(node_id: UUID, parent: "Institution | None") -> str:
    if parent is None:
        return f"/{node_id}/"
    return parent.path + str(node_id) + "/"


def _check_cycle(inst: "Institution", parent: "Institution") -> None:
    if inst.path and parent.path.startswith(inst.path):
        raise ValueError("Setting this parent would create a cycle in the institution hierarchy.")


def _resolve_parent(
    inst: "Institution",
    by_pk: dict[int, "Institution"],
) -> "Institution | None":
    if inst.parent_id is None:
        return None
    if inst.parent_id in by_pk:
        return by_pk[inst.parent_id]
    return cast("Institution", inst.parent)


def _compute_instance_path(
    inst: "Institution",
    by_pk: dict[int, "Institution"],
    computed: set[UUID],
) -> None:
    if inst.node_id in computed:
        return
    parent = _resolve_parent(inst, by_pk)
    if parent and parent.pk in by_pk:
        _compute_instance_path(parent, by_pk, computed)
    if parent:
        _check_cycle(inst, parent)
    inst.path = _compute_path(inst.node_id, parent)
    computed.add(inst.node_id)


def _prepare_instances(objs: Iterable["Institution"]) -> None:
    """Assign node_id and compute path for each instance in topological order.

    Instances are processed so that a parent's path is always computed before
    its children, even when both appear in the same batch.
    """
    instances = list(objs)

    for inst in instances:
        if not inst.node_id:
            inst.node_id = uuid4()

    by_pk: dict[int, "Institution"] = {inst.pk: inst for inst in instances if inst.pk}

    computed: set[UUID] = set()
    for inst in instances:
        _compute_instance_path(inst, by_pk, computed)


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
        _prepare_instances(instances)
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
        _prepare_instances(instances)
        # Ensure path is always updated alongside parent
        fields_with_path = list(fields)
        if "parent" in fields_with_path and "path" not in fields_with_path:
            fields_with_path.append("path")
        return super().bulk_update(instances, fields_with_path, batch_size=batch_size)


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
    node_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    path = models.CharField(max_length=500, db_index=True, default="")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )

    archived_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="When this institution was archived"
    )

    objects = InstitutionManager()
    all_objects = AllInstitutionManager()

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        if not self.node_id:
            self.node_id = uuid4()
        parent = cast(Institution, self.parent) if self.parent_id is not None else None
        if parent is not None:
            _check_cycle(self, parent)
        self.path = _compute_path(self.node_id, parent)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def set_parent(self, parent: "Institution | None") -> None:
        self.parent = parent

    def walk(self) -> Generator["Institution"]:
        yield self
        for child in self.children.all():
            yield from child.walk()

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
