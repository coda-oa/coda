from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Role
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization, FundingRequest
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


def funding_organization() -> FundingOrganization:
    return FundingOrganization.objects.create(name="Test Funder")


def external_funding(funder_id: int | None = None) -> ExternalFunding:
    funder = FundingOrganization.objects.get(pk=funder_id) if funder_id else funding_organization()
    return ExternalFunding.objects.create(
        organization=funder, project_id="1234", project_name="Test Project"
    )


def fundingrequest(title: str = "", author_dto: AuthorDto | None = None) -> FundingRequest:
    _journal = journal()
    affiliation = institution().pk
    author_dto = author_dto or valid_author_dto(affiliation)
    pub_dto = publication_dto(_journal.pk, title=title)
    ext_funding_dto = external_funding_dto(funding_organization().pk)
    return fundingrequest_create(author_dto, pub_dto, ext_funding_dto, cost_dto())


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


def external_funding_dto(organization: int) -> ExternalFundingDto:
    return ExternalFundingDto(
        organization=organization, project_id="1234", project_name="Test Project"
    )


def cost_dto() -> CostDto:
    return CostDto(estimated_cost=100, estimated_cost_currency="USD")
