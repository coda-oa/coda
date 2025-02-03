import random
from datetime import date
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from faker import Faker
from faker.providers import lorem

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.journals.models import Journal
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import LinkType
from coda.apps.publishers.models import Publisher
from coda.author import AuthorNames
from coda.doi import Doi
from coda.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    Payment,
    PaymentMethod,
    ReviewResult,
)
from coda.money import Currency, Money
from coda.publication import JournalId, License, OpenAccessType, Publication, Published
from coda.string import NonEmptyStr

faker = Faker()
faker.add_provider(lorem)


class Command(BaseCommand):
    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--number", type=int, default=1, help="Number of funding requests to create"
        )

    @transaction.atomic
    def handle(self, *args: str, **options: str) -> None:
        number = int(options["number"])
        for _ in range(number):
            review = random.choice([review for review in ReviewResult])
            self.funding_request(review_status=review)

    def funding_request(
        self,
        /,
        review_status: ReviewResult = ReviewResult.Open,
    ) -> None:
        journal = self.journal()
        _ = LinkType.objects.get_or_create(name="DOI")
        subject_area_vocabulary = GlobalPreferences.get_subject_classification_vocabulary()
        publication_types_vocabulary = GlobalPreferences.get_article_publication_type_vocabulary()

        random_subject = random.choice(list(subject_area_vocabulary.concepts))
        random_publication_type = random.choice(list(publication_types_vocabulary.concepts))

        request = FundingRequest.new(
            Publication.new(
                title=NonEmptyStr(faker.sentence()),
                other_authors=AuthorNames(),
                journal=JournalId(journal.pk),
                license=License.CC0,
                open_access_type=OpenAccessType.Gold,
                publication_state=Published(
                    date.fromisoformat(faker.date()),
                    date.fromisoformat(faker.date()),
                ),
                subject_area=random_subject,
                publication_type=random_publication_type,
                links={Doi("10.1234/5678")},
            ),
            Payment(amount=Money(100, Currency.USD), method=PaymentMethod.Direct),
            [
                ExternalFunding(
                    organization=FundingOrganizationId(self.funding_organization().pk),
                    project_id=NonEmptyStr(str(uuid4())),
                    project_name=faker.sentence(),
                )
            ],
            self.extra_contact(),
        )

        id = fundingrequest_create(request)
        request.id = id
        if review_status == ReviewResult.Approved:
            request.approve(Money(100, Currency.EUR))
        elif review_status == ReviewResult.Rejected:
            request.reject()

        repository.save_review(request)

    def extra_contact(self) -> FundingRequestContact:
        return FilledContact(
            name=NonEmptyStr(faker.name()),
            email=faker.email(),
        )

    def publisher(self) -> Publisher:
        return Publisher.objects.first() or Publisher.objects.create(name="Test Publisher")

    def journal(self) -> Journal:
        if Journal.objects.count() > 1:
            all_journals = list(Journal.objects.all())
            return random.choice(all_journals)
        else:
            return Journal.objects.create(
                title="Test Journal", eissn="1234-5678", publisher=self.publisher()
            )

    def funding_organization(self) -> FundingOrganization:
        return FundingOrganization.objects.first() or FundingOrganization.objects.create(
            name="Test Funder"
        )
