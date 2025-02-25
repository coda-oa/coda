from django.db import models

from ._publication import Publication


class PublicationPayment(models.Model):
    status = models.CharField(max_length=20)
    publication = models.OneToOneField(Publication, on_delete=models.DO_NOTHING, related_name="+")
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.DO_NOTHING, null=True)
