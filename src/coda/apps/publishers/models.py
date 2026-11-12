from django.db import models
from typing import ClassVar

from django.urls import reverse


class Publisher(models.Model):
    facet_label_field: ClassVar[str] = "name"
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self) -> str:
        return reverse("publishing:publishers:detail", kwargs={"pk": self.pk})

    def __str__(self) -> str:
        return self.name
