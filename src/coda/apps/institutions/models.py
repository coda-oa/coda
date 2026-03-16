from collections.abc import Generator
from django.db import models


class InstitutionQuerySet(models.QuerySet["Institution"]):
    def archived_only(self) -> "InstitutionQuerySet":
        return self.filter(archived_at__isnull=False)

    def all_with_archived(self) -> "InstitutionQuerySet":
        return self


class InstitutionManager(models.Manager["Institution"]):
    def get_queryset(self) -> InstitutionQuerySet:
        return InstitutionQuerySet(self.model).filter(archived_at__isnull=True)

    def archived_only(self) -> InstitutionQuerySet:
        return InstitutionQuerySet(self.model).archived_only()

    def all_with_archived(self) -> InstitutionQuerySet:
        return InstitutionQuerySet(self.model)


class Institution(models.Model):
    name = models.CharField(max_length=255)
    virtual = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )

    archived_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="When this institution was archived"
    )
    succeeded_by = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="predecessor_of",
        blank=True,
        help_text="The institution(s) that succeeded this one",
    )

    objects = InstitutionManager()
    all_objects = models.Manager()

    def walk(self) -> Generator["Institution"]:
        yield self
        for child in self.children.all():
            yield from child.walk()

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
