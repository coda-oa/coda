from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker
from faker.providers import lorem

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import ProcessingStatus
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.models import LinkType, Publication
from coda.apps.publishers.models import Publisher

faker = Faker()
faker.add_provider(lorem)


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args: str, **options: str) -> None:
        self.funding_request(processing_status=ProcessingStatus.IN_PROGRESS)
        self.funding_request(processing_status=ProcessingStatus.REJECTED)
        self.funding_request(processing_status=ProcessingStatus.APPROVED)

    def funding_request(
        self,
        /,
        processing_status: ProcessingStatus = ProcessingStatus.IN_PROGRESS,
    ) -> None:
        publisher = self.publisher()
        journal = self.journal(publisher)
        doi = LinkType.objects.get(name="DOI")

        request = fundingrequest_create(
            AuthorDto(
                name=faker.name(),
                email=faker.email(),
                orcid=None,
                affiliation=None,
                roles=["SUBMITTER"],
            ),
            PublicationDto(
                title=faker.sentence(),
                journal=journal.pk,
                publication_state=Publication.State.PUBLISHED,
                publication_date=str(date.today()),
                links=[LinkDto(link_type=doi.pk, link_value="10.1234/5678")],
            ),
            FundingDto(estimated_cost=100, estimated_cost_currency="USD"),
        )
        request.processing_status = processing_status.value
        request.save()

    def publisher(self) -> Publisher:
        return Publisher.objects.first() or Publisher.objects.create(name="Test Publisher")

    def journal(self, publisher: Publisher) -> Journal:
        return Journal.objects.first() or Journal.objects.create(
            title="Test Journal", eissn="1234-5678", publisher=publisher
        )
