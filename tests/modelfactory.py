import random

import faker

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.services import author_create
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Creditor, FundingSource, Invoice
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Concept, Publication, Vocabulary
from coda.apps.publishers.models import Publisher
from coda.domain import issn
from coda.domain.contract import PublicationBilling
from coda.domain.fundingrequest import FundingOrganizationId, FundingRequest
from coda.domain.publication import Authors, JournalId
from tests import domainfactory

_faker = faker.Faker()


def _issn() -> str:
    digits = "".join(map(str, random.choices(range(10), k=7)))
    checksum = issn.checksum(digits)
    return f"{digits[:4]}-{digits[4:]}{checksum}"


def institution(enabled: bool = True) -> Institution:
    return Institution.objects.create(name=_faker.company(), virtual=not enabled)


def publisher(name: str = "") -> Publisher:
    return Publisher.objects.create(name=name or _faker.company())


def journal(publisher_id: int | None = None, title: str = "") -> Journal:
    title = title or _faker.sentence()
    return Journal.objects.create(
        title=title, eissn=_issn(), publisher_id=publisher_id or publisher().pk
    )


def author() -> AuthorModel:
    id = author_create(domainfactory.author())
    return AuthorModel.objects.get(pk=id.pk)


def publication(title: str = "") -> Publication:
    title = title or _faker.sentence()
    return Publication.objects.create(title=title, article_journal=journal())


def contract() -> Contract:
    start = _faker.date_this_decade(before_today=True, after_today=False)
    end = _faker.date_this_decade(before_today=False, after_today=True)
    return Contract.objects.create(
        name=_faker.word(),
        start_date=start,
        end_date=end,
        publication_billing=PublicationBilling.Individually.value,
    )


def vocabulary() -> Vocabulary:
    voc = Vocabulary.objects.create(name=_faker.word(), version="1.0")
    concept(voc)
    return voc


def concept(vocabulary: Vocabulary | None = None) -> Concept:
    return Concept.objects.create(
        vocabulary=vocabulary or Vocabulary.objects.create(name=_faker.word(), version="1.0"),
        concept_id=f"{_faker.word()}_{random.randint(1, 1000)}",
        name=_faker.word(),
        hint=_faker.sentence(),
    )


def funding_organization(name: str = "") -> FundingOrganization:
    return FundingOrganization.objects.create(name=name or _faker.company())


def external_funding(funder_id: int | None = None) -> ExternalFunding:
    project_id = random.randint(1000, 9999)
    funder = FundingOrganization.objects.get(pk=funder_id) if funder_id else funding_organization()
    return ExternalFunding.objects.create(
        organization=funder, project_id=project_id, project_name=_faker.sentence()
    )


def fundingrequest(title: str = "", authors: Authors | None = None) -> FundingRequestModel:
    request_id = repository.create(
        FundingRequest.new(
            domainfactory.publication(JournalId(journal().pk), title, relevant_authors=authors),
            domainfactory.payment(),
            external_funding=[
                domainfactory.external_funding(FundingOrganizationId(funding_organization().pk))
            ],
            extra_contact=domainfactory.fundingrequest_contact(),
        )
    )
    return FundingRequestModel.objects.get(pk=request_id.pk)


def invoice() -> Invoice:
    return Invoice.objects.create(
        creditor=creditor(),
        date=_faker.date_this_decade(before_today=False, after_today=True),
        number=_faker.word(),
    )


def creditor(name: str = "") -> Creditor:
    return Creditor.objects.create(name=name or _faker.company())


def budget(name: str = "") -> FundingSource:
    return FundingSource.objects.create(name=name or _faker.company())
