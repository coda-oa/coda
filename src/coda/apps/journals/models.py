from django.db import models
from django.urls import reverse

from coda.apps.publishers.models import Publisher


class Journal(models.Model):
    title = models.CharField(max_length=255)
    eissn = models.CharField(max_length=9)
    licenses = models.CharField(max_length=255, null=True)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="journals")
    open_access_type = models.CharField(max_length=255, null=True)
    successor_to = models.OneToOneField(
        "self", on_delete=models.CASCADE, null=True, related_name="predecessor"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self) -> str:
        return reverse("journals:detail", kwargs={"eissn": self.eissn})
