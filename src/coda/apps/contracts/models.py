import datetime
from django.db import models

from coda.apps.publishers.models import Publisher


class ContractExpiredError(Exception):
    pass


class Contract(models.Model):
    name = models.CharField(max_length=255)
    publishers = models.ManyToManyField(Publisher, related_name="contracts")
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    active_status = models.BooleanField(default=True)

    def is_active(self, now: datetime.date | None = None) -> bool:
        now = now or datetime.date.today()
        start_date = self._ensure_start_date()
        end_date = self._ensure_end_date()
        return start_date <= now <= end_date and self.active_status

    def make_active(
        self, now: datetime.date | None = None, *, until: datetime.date | None = None
    ) -> None:
        now = now or datetime.date.today()
        if until:
            self._raise_if_until_in_past(now, until)
        else:
            self._raise_if_expired(now)

        self.active_status = True
        self.end_date = until
        self.save()

    def make_inactive(self) -> None:
        self.active_status = False
        self.save()

    def _ensure_start_date(self) -> datetime.date:
        return self.start_date or datetime.date.min

    def _ensure_end_date(self) -> datetime.date:
        return self.end_date or datetime.date.max

    def _raise_if_expired(self, now: datetime.date) -> None:
        end_date = self._ensure_end_date()
        if now > end_date:
            raise ContractExpiredError(
                f"Contract {self.name} has already expired on {self.end_date}"
            )

    def _raise_if_until_in_past(self, now: datetime.date, until: datetime.date) -> None:
        if now > until:
            raise ValueError("Until date must be in the future")

    def __str__(self) -> str:
        return self.name
