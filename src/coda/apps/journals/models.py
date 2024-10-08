from django.db import models
from django.urls import reverse

from coda.apps.publishers.models import Publisher


class Journal(models.Model):
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
        return reverse("journals:detail", kwargs={"eissn": self.eissn})

    def __str__(self) -> str:
        return f"{self.title} | {self.publisher.name}"
