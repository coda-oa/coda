import random

import faker

from coda import issn
from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.services import author_create
from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Publication
from coda.apps.publishers.models import Publisher
from coda.author import InstitutionId
from coda.fundingrequest import FundingOrganizationId, FundingRequest
from coda.publication import JournalId
from tests import domainfactory

_faker = faker.Faker()


def _issn() -> str:
    digits = "".join(map(str, random.choices(range(10), k=7)))
    checksum = issn.checksum(digits)
    return f"{digits[:4]}-{digits[4:]}{checksum}"


def institution() -> Institution:
    return Institution.objects.create(name=_faker.company())


def publisher() -> Publisher:
    return Publisher.objects.create(name=_faker.company())


def journal(publisher_id: int | None = None) -> Journal:
    title = _faker.sentence()
    return Journal.objects.create(
        title=title, eissn=_issn(), publisher_id=publisher_id or publisher().id
    )


def author() -> AuthorModel:
    id = author_create(domainfactory.author())
    return AuthorModel.objects.get(pk=id)


def publication(title: str = "") -> Publication:
    title = title or _faker.sentence()
    return Publication.objects.create(title=title, journal=journal(), submitting_author=author())


def funding_organization() -> FundingOrganization:
    return FundingOrganization.objects.create(name=_faker.company())


def external_funding(funder_id: int | None = None) -> ExternalFunding:
    project_id = random.randint(1000, 9999)
    funder = FundingOrganization.objects.get(pk=funder_id) if funder_id else funding_organization()
    return ExternalFunding.objects.create(
        organization=funder, project_id=project_id, project_name=_faker.sentence()
    )


def fundingrequest(title: str = "", _author_dto: AuthorDto | None = None) -> FundingRequestModel:
    request_id = fundingrequest_create(
        FundingRequest.new(
            domainfactory.publication(JournalId(journal().pk), title),
            domainfactory.author(InstitutionId(institution().pk)),
            domainfactory.payment(),
            domainfactory.external_funding(FundingOrganizationId(funding_organization().pk)),
        )
    )
    return FundingRequestModel.objects.get(pk=request_id)
