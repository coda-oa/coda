from collections.abc import Generator
from django.db import models


class Institution(models.Model):
    name = models.CharField(max_length=255)
    virtual = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )

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
