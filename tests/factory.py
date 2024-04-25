import datetime
import random

import faker

from coda import issn, orcid
from coda.apps.authors.dto import AuthorDto, parse_author
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.services import author_create
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import (
    ExternalFunding,
    FundingOrganization,
    FundingRequest,
    PaymentMethod,
)
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.models import License, LinkType, OpenAccessType, Publication
from coda.apps.publishers.models import Publisher
from coda.author import AuthorList, Role

_faker = faker.Faker()


def _issn() -> str:
    digits = "".join(map(str, random.choices(range(10), k=7)))
    checksum = issn.checksum(digits)
    return f"{digits[:4]}-{digits[4:]}{checksum}"


def db_institution() -> Institution:
    return Institution.objects.create(name=_faker.company())


def db_publisher() -> Publisher:
    return Publisher.objects.create(name=_faker.company())


def db_journal() -> Journal:
    title = _faker.sentence()
    return Journal.objects.create(title=title, eissn=_issn(), publisher=db_publisher())


def db_author() -> AuthorModel:
    dto = valid_author_dto()
    author = parse_author(dto)
    return author_create(author)


def db_publication() -> Publication:
    title = _faker.sentence()
    return Publication.objects.create(
        title=title, journal=db_journal(), submitting_author=db_author()
    )


def db_funding_organization() -> FundingOrganization:
    return FundingOrganization.objects.create(name=_faker.company())


def external_funding(funder_id: int | None = None) -> ExternalFunding:
    project_id = random.randint(1000, 9999)
    funder = (
        FundingOrganization.objects.get(pk=funder_id) if funder_id else db_funding_organization()
    )
    return ExternalFunding.objects.create(
        organization=funder, project_id=project_id, project_name=_faker.sentence()
    )


def fundingrequest(title: str = "", author_dto: AuthorDto | None = None) -> FundingRequest:
    _journal = db_journal()
    affiliation = db_institution().pk
    author_dto = author_dto or valid_author_dto(affiliation)
    pub_dto = publication_dto(_journal.pk, title=title)
    ext_funding_dto = external_funding_dto(db_funding_organization().pk)
    return fundingrequest_create(parse_author(author_dto), pub_dto, ext_funding_dto, cost_dto())


def valid_author_dto(affiliation_pk: int | None = None) -> AuthorDto:
    random_roles = random.choices([r.name for r in Role], k=random.randint(1, len(Role)))
    return AuthorDto(
        name=_faker.name(),
        email=_faker.email(),
        orcid=random_orcid(),
        affiliation=affiliation_pk,
        roles=random_roles,
    )


def random_orcid() -> str:
    random_orcid_digits = "".join(map(str, random.choices(range(10), k=15)))
    orcid_checksum = orcid.checksum(random_orcid_digits)
    return "-".join(
        [
            random_orcid_digits[:4],
            random_orcid_digits[4:8],
            random_orcid_digits[8:12],
            random_orcid_digits[12:] + orcid_checksum,
        ]
    )


def publication_dto(
    journal: int, /, title: str = "", links: list[LinkDto] | None = None
) -> PublicationDto:
    random_state = random.choice(
        [
            Publication.State.SUBMITTED,
            Publication.State.PUBLISHED,
            Publication.State.REJECTED,
            Publication.State.ACCEPTED,
        ]
    )

    authors = random_author_names()
    license = _random_license()
    return PublicationDto(
        title=title or _faker.sentence(),
        authors=authors,
        license=license,
        open_access_type=_random_open_access_type(),
        publication_state=random_state,
        publication_date=datetime.date.fromisoformat(_faker.date()),
        journal=journal,
        links=links or link_dtos(),
    )


def random_author_names() -> AuthorList:
    return AuthorList(_faker.name() for _ in range(random.randint(1, 5)))


def _random_license() -> str:
    return random.choice(
        [
            License.CC_BY_NC_ND,
            License.CC_BY_ND,
            License.CC0,
            License.PROPRIETARY,
            License.NONE,
            License.UNKNOWN,
        ]
    ).name


def _random_open_access_type() -> str:
    return random.choice(
        [
            OpenAccessType.GOLD,
            OpenAccessType.HYBRID,
            OpenAccessType.DIAMOND,
            OpenAccessType.CLOSED,
        ]
    ).name


def external_funding_dto(organization: int) -> ExternalFundingDto:
    project_id = str(random.randint(1000, 9999))
    project_name = _faker.sentence()
    return ExternalFundingDto(
        organization=organization, project_id=project_id, project_name=project_name
    )


def cost_dto() -> CostDto:
    payment_method = random.choice([PaymentMethod.DIRECT, PaymentMethod.REIMBURSEMENT])
    return CostDto(
        estimated_cost=100,
        estimated_cost_currency="USD",
        payment_method=payment_method.value,
    )


def link_dtos() -> list[LinkDto]:
    doi, _ = LinkType.objects.get_or_create(name="DOI")
    url, _ = LinkType.objects.get_or_create(name="URL")

    random_doi_suffix = random.randint(1000, 9999)
    doi_link = LinkDto(link_type=int(doi.pk), link_value=f"10.1234/{random_doi_suffix}")
    url_link = LinkDto(link_type=int(url.pk), link_value=_faker.url())
    return [doi_link, url_link]
