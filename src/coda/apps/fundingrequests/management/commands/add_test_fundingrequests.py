from django.core.management.base import BaseCommand

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Publication
from coda.apps.publishers.models import Publisher


class Command(BaseCommand):
    def handle(self, *args: str, **options: str) -> None:
        publisher = self.publisher()
        journal = self.journal(publisher)
        publication = self.publication(journal)
        self.funding_request(publication)

    def publisher(self) -> Publisher:
        return Publisher.objects.first() or Publisher.objects.create(name="Test Publisher")

    def journal(self, publisher: Publisher) -> Journal:
        return Journal.objects.first() or Journal.objects.create(
            title="Test Journal", eissn="1234-5678", publisher=publisher
        )

    def publication(self, journal: Journal) -> Publication:
        return Publication.objects.create(title="Test Publication", journal=journal)

    def funding_request(self, publication: Publication) -> None:
        FundingRequest.objects.create(
            publication=publication,
            estimated_cost=100,
            estimated_cost_currency="USD",
            processing_status="in_progress",
        )
