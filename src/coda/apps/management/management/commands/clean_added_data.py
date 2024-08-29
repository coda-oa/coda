from django.core.management import BaseCommand
from django.db import transaction

from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.invoices.models import Invoice
from coda.apps.publications.models import Publication


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args: str, **options: str) -> None:
        FundingRequest.objects.all().delete()
        Label.objects.all().delete()
        Invoice.objects.all().delete()
        Publication.objects.all().delete()
