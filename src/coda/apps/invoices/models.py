from django.db import models
from django.urls import reverse

from coda.apps.publications.models import Publication


class FundingSource(models.Model):
    name = models.CharField(max_length=255)


class Creditor(models.Model):
    name = models.CharField(max_length=255)

    def get_absolute_url(self) -> str:
        return reverse("invoices:creditor_detail", kwargs={"pk": self.pk})

    def __str__(self) -> str:
        return self.name


class Invoice(models.Model):
    creditor = models.ForeignKey(Creditor, on_delete=models.CASCADE)
    date = models.DateField()
    number = models.CharField(max_length=255)
    comment = models.TextField(blank=True)

    def get_absolute_url(self) -> str:
        return reverse("invoices:detail", kwargs={"pk": self.pk})


class Position(models.Model):
    description = models.TextField()
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, null=True)
    cost_amount = models.DecimalField(max_digits=10, decimal_places=4)
    cost_currency = models.CharField(max_length=3)
    cost_type = models.CharField(max_length=255, default="other")
    tax_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    funding_source = models.ForeignKey(FundingSource, on_delete=models.CASCADE, null=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="positions")
