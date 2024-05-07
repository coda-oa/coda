from datetime import date
from uuid import uuid4

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker
from faker.providers import lorem

from coda.apps.fundingrequests.models import FundingOrganization, ProcessingStatus
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.journals.models import Journal
from coda.apps.publications.models import LinkType
from coda.apps.publishers.models import Publisher
from coda.author import Author, AuthorList, Role
from coda.doi import Doi
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    Payment,
    PaymentMethod,
)
from coda.money import Money, Currency
from coda.publication import (
    JournalId,
    License,
    OpenAccessType,
    Publication,
    Published,
)
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
        _ = LinkType.objects.get_or_create(name="DOI")

        fundingrequest_create(
            FundingRequest.new(
                Publication.new(
                    title=NonEmptyStr(faker.sentence()),
                    authors=AuthorList(),
                    journal=JournalId(journal.pk),
                    license=License.CC0,
                    open_access_type=OpenAccessType.Gold,
                    publication_state=Published(date.fromisoformat(faker.date())),
                    links={Doi("10.1234/5678")},
                ),
                Author.new(
                    name=NonEmptyStr(faker.name()),
                    email=faker.email(),
                    orcid=None,
                    affiliation=None,
                    roles=[Role.SUBMITTER],
                ),
                Payment(amount=Money(100, Currency.USD), method=PaymentMethod.DIRECT),
                ExternalFunding(
                    organization=FundingOrganizationId(self.funding_organization().pk),
                    project_id=NonEmptyStr(str(uuid4())),
                    project_name=faker.sentence(),
                ),
            ),
        )

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
