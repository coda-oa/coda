from datetime import datetime, timedelta
from typing import Any

from django.db import models
from django.utils import timezone

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


class JournalBlockReason(models.TextChoices):
    MIRROR = "MIRROR", "Mirror"
    PREDATORY = "PREDATORY", "Predatory"


class BlockedJournal(models.Model):
    blocklist = models.ForeignKey("BlockList", on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE)
    reason = models.CharField(max_length=255, choices=JournalBlockReason)
    confirmed_at = models.DateTimeField(auto_now_add=True)

    def get_journal_id(self) -> int:
        return self.journal.pk

    def get_title(self) -> str:
        return self.journal.title

    def get_publisher(self) -> str:
        return self.journal.publisher.name

    def confirm_block(self, now: datetime | None = None) -> None:
        self.confirmed_at = now or timezone.now()
        self.save()

    class Meta:
        unique_together = ("blocklist", "journal")


class BlockedPublisher(models.Model):
    blocklist = models.ForeignKey("BlockList", on_delete=models.CASCADE)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE)
    confirmed_at = models.DateTimeField(auto_now_add=True)

    def get_name(self) -> str:
        return self.publisher.name

    class Meta:
        unique_together = ("blocklist", "publisher")


class _SingletonManager(models.Manager["BlockList"]):
    def create(self, **kwargs: Any) -> "BlockList":
        if self.get_queryset().exists():
            return self.get_queryset().get()

        return super().create(**kwargs)

    def get(self) -> "BlockList":
        return self.get_or_create()[0]


class BlockList(models.Model):
    objects = _SingletonManager()

    SIX_MONTHS = 30 * 6
    name = models.CharField(max_length=255, default="Blocklist")
    recommend_review_after = models.DurationField(default=timedelta(days=SIX_MONTHS))

    def block_journal(self, journal: Journal, reason: str, now: datetime | None = None) -> None:
        blocked_journal = BlockedJournal.objects.filter(blocklist=self, journal=journal)
        now = now or timezone.now()
        if blocked_journal.exists():
            blocked_journal.update(reason=reason, confirmed_at=now)
            return

        BlockedJournal.objects.create(
            blocklist=self, journal=journal, reason=reason, confirmed_at=now
        )

    def unblock_journal(self, journal: Journal) -> None:
        BlockedJournal.objects.filter(blocklist=self, journal=journal).delete()

    def block_publisher(self, publisher: Publisher, now: datetime | None = None) -> None:
        BlockedPublisher.objects.create(
            blocklist=self, publisher=publisher, confirmed_at=now or timezone.now()
        )

    def unblock_publisher(self, publisher: Publisher) -> None:
        BlockedPublisher.objects.filter(blocklist=self, publisher=publisher).delete()

    def blocked_journals(self) -> models.QuerySet[BlockedJournal]:
        return BlockedJournal.objects.filter(blocklist=self)

    def blocked_publishers(self) -> models.QuerySet[BlockedPublisher]:
        return BlockedPublisher.objects.filter(blocklist=self)

    def journals_to_review(self, now: datetime | None = None) -> models.QuerySet[Journal]:
        return Journal.objects.filter(
            blockedjournal__blocklist=self,
            blockedjournal__confirmed_at__lt=now or timezone.now() - self.recommend_review_after,
        )

    def confirm_journal_block(self, journal: Journal, now: datetime | None = None) -> None:
        blocked_journal = BlockedJournal.objects.get(blocklist=self, journal=journal)
        blocked_journal.confirm_block(now)

    def is_journal_blocked(self, journal: Journal) -> bool:
        return BlockedJournal.objects.filter(blocklist=self, journal=journal).exists()

    def is_publisher_blocked(self, publisher: Publisher) -> bool:
        return BlockedPublisher.objects.filter(blocklist=self, publisher=publisher).exists()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = 1
        super().save()
