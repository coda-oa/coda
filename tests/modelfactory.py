import random

import faker

from coda import issn
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.services import author_create
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Creditor, FundingSource
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Concept, Publication, Vocabulary
from coda.apps.publishers.models import Publisher
from coda.author import Author, InstitutionId
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
    return Publication.objects.create(
        title=title, article_journal=journal(), submitting_author=author()
    )


def contract() -> Contract:
    start = _faker.date_this_decade(before_today=True, after_today=False)
    end = _faker.date_this_decade(before_today=False, after_today=True)
    return Contract.objects.create(name=_faker.word(), start_date=start, end_date=end)


def vocabulary() -> Vocabulary:
    voc = Vocabulary.objects.create(name=_faker.word(), version="1.0")
    concept(voc)
    return voc


def concept(vocabulary: Vocabulary | None = None) -> Concept:
    return Concept.objects.create(
        vocabulary=vocabulary or Vocabulary.objects.create(name=_faker.word(), version="1.0"),
        concept_id=f"{_faker.word()}_{random.randint(1,1000)}",
        name=_faker.word(),
        hint=_faker.sentence(),
    )


def funding_organization() -> FundingOrganization:
    return FundingOrganization.objects.create(name=_faker.company())


def external_funding(funder_id: int | None = None) -> ExternalFunding:
    project_id = random.randint(1000, 9999)
    funder = FundingOrganization.objects.get(pk=funder_id) if funder_id else funding_organization()
    return ExternalFunding.objects.create(
        organization=funder, project_id=project_id, project_name=_faker.sentence()
    )


def fundingrequest(title: str = "", submitter: Author | None = None) -> FundingRequestModel:
    request_id = fundingrequest_create(
        FundingRequest.new(
            domainfactory.publication(JournalId(journal().pk), title),
            submitter or domainfactory.author(InstitutionId(institution().pk)),
            domainfactory.payment(),
            [domainfactory.external_funding(FundingOrganizationId(funding_organization().pk))],
        )
    )
    return FundingRequestModel.objects.get(pk=request_id)


def creditor() -> Creditor:
    return Creditor.objects.create(name=_faker.company())


def funding_source() -> FundingSource:
    return FundingSource.objects.create(name=_faker.company())
