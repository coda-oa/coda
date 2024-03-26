from django.db import models

from coda.apps.publishers.models import Publisher


class Contract(models.Model):
    name = models.CharField(max_length=255)
    publishers = models.ManyToManyField(Publisher, related_name="contracts")
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name
