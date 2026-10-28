from typing import ClassVar

from django.db import models
from django.urls import reverse

from coda.apps.publishers.models import Publisher


class Journal(models.Model):
    #: The field facets use as this model's display label. Distinct from
    #: __str__ when a dropdown wants context the facet pipeline must not
    #: include (the "title | publisher" history).
    facet_label_field: ClassVar[str] = "title"
    title = models.TextField()
    eissn = models.CharField(max_length=9)
    licenses = models.CharField(max_length=255, null=True)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="journals")
    predecessor = models.OneToOneField(
        "self", on_delete=models.CASCADE, null=True, related_name="successor"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self) -> str:
        return reverse("publishing:journals:detail", kwargs={"eissn": self.eissn})

    def __str__(self) -> str:
        return self.title
