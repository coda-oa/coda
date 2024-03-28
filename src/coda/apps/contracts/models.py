import datetime
from django.db import models

from coda.apps.publishers.models import Publisher


class Contract(models.Model):
    name = models.CharField(max_length=255)
    publishers = models.ManyToManyField(Publisher, related_name="contracts")
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    active_status = models.BooleanField(default=True)

    def is_active(self, now: datetime.date | None = None) -> bool:
        now = now or datetime.date.today()
        start_date = self.start_date or datetime.date.min
        end_date = self.end_date or datetime.date.max
        return start_date <= now <= end_date

    def __str__(self) -> str:
        return self.name
