from django.db import models

from ._publication import Publication


class PublicationPayment(models.Model):
    status = models.CharField(max_length=20)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, null=True)
