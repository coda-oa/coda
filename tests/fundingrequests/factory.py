from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.models import Publication
from coda.apps.publishers.models import Publisher
from tests import test_orcid


def institution() -> Institution:
    return Institution.objects.create(name="Test Institution")


def publisher() -> Publisher:
    return Publisher.objects.create(name="Test Publisher")


def journal() -> Journal:
    return Journal.objects.create(title="Test Journal", eissn="1234-5678", publisher=publisher())


def publication() -> Publication:
    return Publication.objects.create(
        title="Test Publication",
        journal=journal(),
    )


def valid_author_dto(affiliation_pk: int) -> AuthorDto:
    return AuthorDto(
        name="Josiah Carberry",
        email="carberry@example.com",
        orcid=test_orcid.JOSIAH_CARBERRY,
        affiliation=affiliation_pk,
    )


def publication_dto(journal_pk: int) -> PublicationDto:
    return PublicationDto(
        title="My Paper",
        journal=journal_pk,
        publication_state="submitted",
        publication_date="2021-01-01",
    )


def funding_dto() -> FundingDto:
    return FundingDto(estimated_cost=100, estimated_cost_currency="USD")
