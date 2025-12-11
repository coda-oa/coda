from django.db import models
from django.urls import reverse

from coda.apps.contracts.models import Contract
from coda.apps.institutions.models import Institution
from coda.apps.publications.models import Publication


class FundingSource(models.Model):
    class TypeChoices(models.TextChoices):
        budget = ("budget", "Budget")
        institution = ("institution", "Institution")

    type = models.CharField(max_length=255, default="budget", choices=TypeChoices)
    name = models.CharField(max_length=255, blank=True)
    institution = models.ForeignKey(Institution, null=True, on_delete=models.CASCADE)


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
    status = models.CharField(max_length=255, default="unpaid")
    comment = models.TextField(blank=True)
    external_invoice_id = models.CharField(max_length=255, blank=True)

    def get_absolute_url(self) -> str:
        return reverse("invoices:detail", kwargs={"pk": self.pk})


class Position(models.Model):
    description = models.TextField()
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, null=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True)
    contract_year = models.IntegerField(null=True)

    cost_amount = models.DecimalField(max_digits=20, decimal_places=4)
    cost_currency = models.CharField(max_length=3)
    cost_type = models.CharField(max_length=255, default="other")
    tax_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="positions")
    external_position_id = models.CharField(max_length=255, blank=True)


class FundingAssignment(models.Model):
    position = models.ForeignKey(
        Position,
        related_name="funding_assignments",
        on_delete=models.CASCADE,
    )
    funding_source = models.ForeignKey(
        FundingSource,
        related_name="funding_assignments",
        on_delete=models.PROTECT,
        null=True,
    )
    amount = models.DecimalField(max_digits=20, decimal_places=4)


class CurrencyConversion(models.Model):
    target_currency = models.CharField(max_length=3)
    exchange_rate = models.DecimalField(max_digits=11, decimal_places=4)

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="currency_conversions",
    )
