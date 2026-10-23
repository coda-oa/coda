import random
from datetime import date
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from faker import Faker
from faker.providers import lorem

from coda.apps.authors.models import Author
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import (
    FundingOrganization,
)
from coda.apps.fundingrequests.models import (
    FundingRequest as FundingRequestModel,
)
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import LinkType
from coda.apps.publishers.models import Publisher
from coda.domain.author import AuthorNames, Role
from coda.domain.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    Payment,
    PaymentMethod,
    Review,
)
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, License, OpenAccessType, Publication, Published
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr

faker = Faker()
faker.add_provider(lorem)

#: How much likelier a faculty-level institution is to receive an affiliation
#: than an institute-level one. Faculties are few and big; the treemap reads
#: better when the weight distribution mirrors that.
FACULTY_WEIGHT = 30
INSTITUTE_WEIGHT = 1


class Command(BaseCommand):
    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--number", type=int, default=1, help="Number of funding requests to create"
        )
        parser.add_argument(
            "--backfill-affiliations",
            action="store_true",
            help="Assign weighted random affiliations to every funding request whose "
            "corresponding author has none (requests created before this command "
            "grew author support), instead of creating new requests",
        )

    @transaction.atomic
    def handle(self, *args: str, **options: str) -> None:
        if options["backfill_affiliations"]:
            self.backfill_affiliations()
            return
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
            external_funding=[
                ExternalFunding(
                    organization=FundingOrganizationId(self.funding_organization().pk),
                    project_id=NonEmptyStr(str(uuid4())),
                    project_name=faker.sentence(),
                )
            ],
            extra_contact=self.extra_contact(),
        )

        request.id = repository.create(request)

        assert request.publication.id is not None  # just created
        self.attach_corresponding_author(request.publication.id)
        review = Review(
            request.id,
            decided_funding=Money(100, Currency.EUR),
            remarks=faker.sentence(),
            result=review_status,
        )

        repository.save_review(review)

    def backfill_affiliations(self) -> None:
        """Attach a weighted-affiliation corresponding author to every funding
        request that has none. Requests whose publication already has an
        affiliated corresponding author are left alone."""
        missing = FundingRequestModel.objects.exclude(
            publication__relevant_authors__affiliation__isnull=False
        )
        count = 0
        for request in missing.only("pk", "publication_id").iterator():
            self.attach_corresponding_author(request.publication_id)
            count += 1
        self.stdout.write(f"Affiliated {count} funding requests.")

    def extra_contact(self) -> FundingRequestContact:
        return FilledContact(
            name=NonEmptyStr(faker.name()),
            email=faker.email(),
        )

    def weighted_affiliation(self) -> Institution | None:
        """A pseudo-random affiliation, faculties weighted over institutes so
        the treemap's big blocks dominate the small ones."""
        institutions = list(Institution.objects.exclude(parent__isnull=True))
        if not institutions:
            return None
        weights = [
            FACULTY_WEIGHT if inst.parent and inst.parent.parent_id is None else INSTITUTE_WEIGHT
            for inst in institutions
        ]
        return random.choices(institutions, weights=weights, k=1)[0]

    def attach_corresponding_author(self, publication_id: int) -> None:
        """One corresponding author per request, affiliated per the weighted
        distribution. The reporting dataset derives the institution dimension
        from corresponding authors only."""
        affiliation = self.weighted_affiliation()
        Author.objects.create(
            name=faker.name(),
            email=faker.email(),
            publication_id=publication_id,
            affiliation=affiliation,
            roles=Role.CORRESPONDING_AUTHOR.name,
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
