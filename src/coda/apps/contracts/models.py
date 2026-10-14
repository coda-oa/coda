from django.db import models
from django.utils import timezone

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


class ContractQuerySet(models.QuerySet["Contract"]):
    def active(self) -> "ContractQuerySet":
        """Contracts whose period contains today. Null bounds are unbounded."""
        today = timezone.localdate()
        return self.filter(
            models.Q(start_date__isnull=True) | models.Q(start_date__lte=today),
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today),
        )


class Contract(models.Model):
    objects = ContractQuerySet.as_manager()

    name = models.CharField(max_length=255)
    publishers = models.ManyToManyField(Publisher, related_name="contracts")
    journals = models.ManyToManyField(Journal, related_name="contracts")
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    publication_billing = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name


class ContractLinkType(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.name


class ContractLink(models.Model):
    type = models.ForeignKey(ContractLinkType, on_delete=models.CASCADE)
    value = models.TextField()
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="links")

    def __str__(self) -> str:
        return f"{self.type.name}: {self.value}"
