from collections.abc import Generator
from django.db import models


class Institution(models.Model):
    name = models.CharField(max_length=255)
    virtual = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )

    def walk(self) -> Generator["Institution", None, None]:
        yield self
        for child in self.children.all():
            yield from child.walk()

    def __str__(self) -> str:
        return self.name
