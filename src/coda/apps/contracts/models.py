from django.db import models

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


class Contract(models.Model):
    name = models.CharField(max_length=255)
    publishers = models.ManyToManyField(Publisher, related_name="contracts")
    journals = models.ManyToManyField(Journal, related_name="contracts")
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    active_status = models.BooleanField(default=True)
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
