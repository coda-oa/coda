from django.db import models
from django.urls import reverse

from coda.apps.publications.models import Publication
from coda.apps.publishers.models import Publisher


class FundingSource(models.Model):
    name = models.CharField(max_length=255)


class Invoice(models.Model):
    recipient = models.ForeignKey(Publisher, on_delete=models.CASCADE)
    number = models.CharField(max_length=255)

    def get_absolute_url(self) -> str:
        return reverse("invoices:detail", kwargs={"pk": self.pk})


class Position(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    cost_amount = models.DecimalField(max_digits=10, decimal_places=4)
    cost_currency = models.CharField(max_length=3)
    description = models.TextField()
    funding_source = models.ForeignKey(FundingSource, on_delete=models.CASCADE, null=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="positions")
