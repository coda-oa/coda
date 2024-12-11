from django.db import models
from django.urls import reverse


class Publisher(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self) -> str:
        return reverse("publishers:detail", kwargs={"pk": self.pk})

    def __str__(self) -> str:
        return self.name
