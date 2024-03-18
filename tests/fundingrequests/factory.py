from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Role
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
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


def fundingrequest(title: str = "", author_dto: AuthorDto | None = None) -> FundingRequest:
    _journal = journal()
    affiliation = institution().pk
    author_dto = author_dto or valid_author_dto(affiliation)
    pub_dto = publication_dto(_journal.pk, title=title)
    return fundingrequest_create(author_dto, pub_dto, funding_dto())


def valid_author_dto(affiliation_pk: int | None = None) -> AuthorDto:
    return AuthorDto(
        name="Josiah Carberry",
        email="carberry@example.com",
        orcid=test_orcid.JOSIAH_CARBERRY,
        affiliation=affiliation_pk,
        roles=[Role.CORRESPONDING_AUTHOR.name],
    )


def publication_dto(
    journal: int, /, title: str = "", links: list[LinkDto] | None = None
) -> PublicationDto:
    return PublicationDto(
        title=title or "My Paper",
        publication_state="submitted",
        publication_date="2021-01-01",
        journal=journal,
        links=links or [],
    )


def funding_dto() -> FundingDto:
    return FundingDto(estimated_cost=100, estimated_cost_currency="USD")
