import random
from datetime import date
from typing import cast

import faker

from coda import orcid
from coda.author import Author, AuthorId, AuthorList, InstitutionId, Role
from coda.doi import Doi
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
    PaymentMethod,
)
from coda.invoice import (
    CostType,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    Position,
    Positions,
    TaxRate,
)
from coda.money import Currency, Money
from coda.publication import (
    JournalId,
    License,
    MediaPublicationStates,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
)
from coda.string import NonEmptyStr

_faker = faker.Faker()


def author(affiliation: InstitutionId | None = None, id: AuthorId | None = None) -> Author:
    return Author(
        id=id,
        name=NonEmptyStr(_faker.name()),
        email=_faker.email(),
        orcid=random_orcid(),
        affiliation=affiliation,
        roles=frozenset(random_roles()),
    )


def invoice(
    id: InvoiceId | None = None,
    creditor: CreditorId | None = None,
    positions: Positions = (),
) -> Invoice:
    return Invoice(
        id=id,
        date=date.fromisoformat(_faker.date()),
        number=NonEmptyStr(_faker.uuid4()),
        creditor=creditor or CreditorId(random.randint(1, 1000)),
        positions=positions or [publication_position() for n in range(random.randint(1, 5))],
    )


def publication_position(
    publication: PublicationId | None = None,
    currency: Currency | None = None,
    funding_source: FundingSourceId | None = None,
) -> Position[PublicationId]:
    return Position(
        item=publication or PublicationId(random.randint(1, 1000)),
        cost=random_money(currency),
        cost_type=random.choice(list(CostType)),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
        funding_source=funding_source,
    )


def free_position() -> Position[str]:
    return Position(
        item=_faker.sentence(),
        cost=random_money(),
        cost_type=random.choice(list(CostType)),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
    )


def publication(
    journal: JournalId | None = None, title: str = "", id: PublicationId | None = None
) -> Publication:
    print_state = cast(
        PublicationState,
        random.choice([Unpublished(), Published(date.fromisoformat(_faker.date()))]),
    )

    online_state = cast(
        PublicationState,
        random.choice([Unpublished(), Published(date.fromisoformat(_faker.date()))]),
    )

    return Publication(
        id=id,
        title=NonEmptyStr(title or _faker.sentence()),
        journal=journal or JournalId(random.randint(1, 1000)),
        authors=random_authorlist(),
        license=random_license(),
        open_access_type=random_open_access_type(),
        publication_state=MediaPublicationStates(
            online=online_state,
            print=print_state,
        ),
        links={Doi("10.1234/5678")},
    )


def payment() -> Payment:
    money = random_money()
    method = random.choice([m for m in PaymentMethod])
    return Payment(amount=money, method=method)


def random_money(currency: Currency | None = None) -> Money:
    amount = random.random() * random.randint(1, 1000)
    currency = currency or random.choice([c for c in Currency])
    money = Money(str(amount), currency)
    return money


def external_funding(organization_id: FundingOrganizationId | None = None) -> ExternalFunding:
    return ExternalFunding(
        organization=organization_id or FundingOrganizationId(random.randint(1, 1000)),
        project_id=NonEmptyStr(str(_faker.uuid4())),
        project_name=_faker.sentence(),
    )


def fundingrequest(
    *,
    id: FundingRequestId | None = None,
    journal_id: JournalId | None = None,
    funding_org_id: FundingOrganizationId | None = None,
) -> FundingRequest:
    return FundingRequest(
        id=id or None,
        publication=publication(journal_id or JournalId(random.randint(1, 1000))),
        submitter=author(),
        estimated_cost=payment(),
        external_funding=external_funding(funding_org_id),
    )


def random_authorlist() -> AuthorList:
    return AuthorList(_faker.name() for _ in range(random.randint(1, 5)))


def random_orcid() -> orcid.Orcid:
    random_orcid_digits = "".join(map(str, random.choices(range(10), k=15)))
    orcid_checksum = orcid.checksum(random_orcid_digits)
    return orcid.Orcid(
        "-".join(
            [
                random_orcid_digits[:4],
                random_orcid_digits[4:8],
                random_orcid_digits[8:12],
                random_orcid_digits[12:] + orcid_checksum,
            ]
        )
    )


def random_roles() -> list[Role]:
    return random.choices([r for r in Role], k=random.randint(1, len(Role)))


def random_license() -> License:
    return random.choice([li for li in License])


def random_open_access_type() -> OpenAccessType:
    return random.choice(
        [
            OpenAccessType.Gold,
            OpenAccessType.Hybrid,
            OpenAccessType.Diamond,
            OpenAccessType.Closed,
        ]
    )
