import random
from typing import TypedDict

import faker

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.publications.dto import JournalDto, LinkDto, PublicationDto, PublicationMetaDto
from coda.fundingrequest import PaymentMethod
from coda.publication import Published, UnknownConcept, UnpublishedState, VocabularyConcept
from tests.domainfactory import (
    random_authorlist,
    random_license,
    random_open_access_type,
    random_orcid,
    random_roles,
)

_faker = faker.Faker()


def author_dto(affiliation_id: int | None = None) -> AuthorDto:
    return AuthorDto(
        name=_faker.name(),
        email=_faker.email(),
        orcid=random_orcid(),
        affiliation=affiliation_id,
        roles=[r.name for r in random_roles()],
    )


def publication_dto(
    journal: int,
    /,
    title: str = "",
    publication_type: VocabularyConcept = UnknownConcept,
    subject_area: VocabularyConcept = UnknownConcept,
    contracts: list[int] = [],
    links: list[LinkDto] | None = None,
) -> PublicationDto:
    return PublicationDto(
        meta=publication_meta_dto(title, publication_type, subject_area),
        authors=list(random_authorlist()),
        journal=JournalDto({"journal_id": journal}),
        links=links or link_dtos(),
        contracts=[],
    )


def publication_meta_dto(
    title: str = "",
    publication_type: VocabularyConcept = UnknownConcept,
    subject_area: VocabularyConcept = UnknownConcept,
) -> PublicationMetaDto:
    state = random.choice([_unpublished_data(), _published_data()])
    return PublicationMetaDto(
        {
            "title": title or _faker.sentence(),
            "license": random_license().name,
            "publication_type": publication_type.id,
            "publication_type_vocabulary": publication_type.vocabulary,
            "subject_area": subject_area.id,
            "subject_area_vocabulary": subject_area.vocabulary,
            "open_access_type": random_open_access_type().name,
            **state,
        }
    )


class State(TypedDict):
    publication_state: str
    online_publication_date: str
    print_publication_date: str


def _unpublished_data() -> State:
    return State(
        {
            "publication_state": random.choice([s.name for s in UnpublishedState]),
            "online_publication_date": "",
            "print_publication_date": "",
        }
    )


def _published_data() -> State:
    return State(
        {
            "publication_state": Published.name(),
            "online_publication_date": _faker.date(),
            "print_publication_date": _faker.date(),
        }
    )


def external_funding_dto(organization: int) -> ExternalFundingDto:
    project_id = str(random.randint(1000, 9999))
    project_name = _faker.sentence()
    return ExternalFundingDto(
        organization=organization, project_id=project_id, project_name=project_name
    )


def cost_dto() -> CostDto:
    payment_method = random.choice([PaymentMethod.Direct, PaymentMethod.Reimbursement])
    return CostDto(
        estimated_cost=100,
        estimated_cost_currency="USD",
        payment_method=payment_method.value,
    )


def link_dtos() -> list[LinkDto]:
    random_doi_suffix = random.randint(1000, 9999)
    doi_link = LinkDto(link_type="DOI", link_value=f"10.1234/{random_doi_suffix}")
    url_link = LinkDto(link_type="URL", link_value=_faker.url())
    return [doi_link, url_link]
