from datetime import date
from uuid import uuid4

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker
from faker.providers import lorem

from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import FundingOrganization, PaymentMethod, ProcessingStatus
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.models import License, LinkType, OpenAccessType, Publication
from coda.apps.publishers.models import Publisher
from coda.author import Author, AuthorList, Role
from coda.string import NonEmptyStr

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
            Author.new(
                name=NonEmptyStr(faker.name()),
                email=faker.email(),
                orcid=None,
                affiliation=None,
                roles=[Role.SUBMITTER],
            ),
            PublicationDto(
                title=faker.sentence(),
                authors=AuthorList(),
                journal=journal.pk,
                license=License.CC0.name,
                open_access_type=OpenAccessType.GOLD.name,
                publication_state=Publication.State.PUBLISHED,
                publication_date=date.fromisoformat(faker.date()),
                links=[LinkDto(link_type=doi.pk, link_value="10.1234/5678")],
            ),
            ExternalFundingDto(
                organization=self.funding_organization().pk,
                project_id=str(uuid4()),
                project_name=faker.sentence(),
            ),
            CostDto(
                estimated_cost=100,
                estimated_cost_currency="USD",
                payment_method=PaymentMethod.DIRECT.value,
            ),
        )
        request.processing_status = processing_status.value
        request.save()

    def publisher(self) -> Publisher:
        return Publisher.objects.first() or Publisher.objects.create(name="Test Publisher")

    def journal(self, publisher: Publisher) -> Journal:
        return Journal.objects.first() or Journal.objects.create(
            title="Test Journal", eissn="1234-5678", publisher=publisher
        )

    def funding_organization(self) -> FundingOrganization:
        return FundingOrganization.objects.first() or FundingOrganization.objects.create(
            name="Test Funder"
        )
