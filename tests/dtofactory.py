import random
from typing import Any, cast

import faker

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.fundingrequest import PaymentMethod
from coda.publication import Published, UnpublishedState
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
    journal: int, /, title: str = "", links: list[LinkDto] | None = None
) -> PublicationDto:
    online_state = random.choice([_unpublished_data("online"), _published_data("online")])
    print_state = random.choice([_unpublished_data("print"), _published_data("print")])
    return cast(
        PublicationDto,
        {
            "title": title or _faker.sentence(),
            "authors": list(random_authorlist()),
            "license": random_license().name,
            "open_access_type": random_open_access_type().name,
            "journal": journal,
            "links": links or link_dtos(),
            **online_state,
            **print_state,
        },
    )


def _unpublished_data(media: str) -> dict[str, Any]:
    return {
        f"{media}_publication_state": random.choice([s.name for s in UnpublishedState]),
        f"{media}_publication_date": None,
    }


def _published_data(media: str) -> dict[str, Any]:
    return {
        f"{media}_publication_state": Published.name(),
        f"{media}_publication_date": _faker.date(),
    }


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
