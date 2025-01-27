import random
from datetime import date
from decimal import Decimal
from typing import cast

import faker

from coda import orcid
from coda.author import Author, AuthorId, AuthorList, InstitutionId, Role
from coda.contract import Contract, ContractId, ContractYear, PublisherId
from coda.date import DateRange
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
    PaymentStatus,
    Position,
    Positions,
    TaxRate,
)
from coda.money import Currency, Money
from coda.publication import (
    JournalId,
    License,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
)
from coda.string import NonEmptyStr
from coda.vocabulary import UnknownConcept, VocabularyConcept

_faker = faker.Faker()


class _NoRole:
    __slots__ = ()
    __instance: "_NoRole | None" = None

    def __new__(cls) -> "_NoRole":
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)

        return cls.__instance


NoRole = _NoRole()


def author(
    affiliation: InstitutionId | None = None,
    *,
    role: Role | _NoRole | None = None,
    id: AuthorId | None = None,
) -> Author:
    if role == NoRole:
        role = Role.CO_AUTHOR
    elif role is None:
        role = random_role()

    return Author(
        id=id,
        name=NonEmptyStr(_faker.name()),
        email=_faker.email(),
        orcid=random_orcid(),
        affiliation=affiliation,
        role=cast(Role, role),
    )


def contract(id: ContractId | None = None, period: DateRange | None = None) -> Contract:
    if period is None:
        start = _faker.date_this_decade(before_today=True, after_today=False)
        end = _faker.date_this_decade(before_today=False, after_today=True)
        period = DateRange.create(start=start, end=end)

    return Contract(
        id=id,
        name=NonEmptyStr(_faker.sentence()),
        publishers=(),
        period=period,
    )


def contract_year(contract: Contract) -> ContractYear:
    def _pick_year_from_contract_period(c: Contract) -> int:
        return _faker.date_between_dates(c.period.start, c.period.end).year

    return contract.in_year(year=_pick_year_from_contract_period(contract))


def invoice(
    id: InvoiceId | None = None,
    creditor: CreditorId | None = None,
    positions: Positions = (),
) -> Invoice:
    status = random.choice([s for s in PaymentStatus])
    return Invoice(
        id=id,
        date=date.fromisoformat(_faker.date()),
        number=NonEmptyStr(str(_faker.uuid4())),
        creditor=creditor or CreditorId(random.randint(1, 1000)),
        positions=positions or [publication_position() for n in range(random.randint(1, 5))],
        status=status,
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


def contract_position(
    contract: ContractYear,
    currency: Currency | None = None,
    funding_source: FundingSourceId | None = None,
) -> Position[ContractYear]:
    return Position(
        item=contract,
        cost=random_money(currency),
        cost_type=random.choice(list(CostType)),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
        funding_source=funding_source,
    )


def free_position(currency: Currency | None = None) -> Position[str]:
    return Position(
        item=_faker.sentence(),
        cost=random_money(currency),
        cost_type=random.choice(list(CostType)),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
    )


def publication(
    journal: JournalId | None = None,
    title: str = "",
    publication_type: VocabularyConcept | None = None,
    subject_area: VocabularyConcept | None = None,
    contracts: tuple[ContractYear, ...] = (),
    *,
    id: PublicationId | None = None,
) -> Publication:
    state = cast(
        PublicationState, random.choice([Unpublished(), Published(_random_date(), _random_date())])
    )

    return Publication(
        id=id,
        title=NonEmptyStr(title or _faker.sentence()),
        journal=journal or JournalId(random.randint(1, 1000)),
        corresponding_author=author(),
        authors=random_authorlist(),
        license=random_license(),
        publication_type=publication_type or UnknownConcept,
        subject_area=subject_area or UnknownConcept,
        open_access_type=random_open_access_type(),
        publication_state=state,
        contracts=contracts,
        links={Doi("10.1234/5678")},
    )


def monograph(
    publisher: PublisherId | None = None,
    contracts: tuple[ContractYear, ...] = (),
    publication_type: VocabularyConcept | None = None,
    subject_area: VocabularyConcept | None = None,
    *,
    id: PublicationId | None = None,
) -> Monograph:
    return Monograph(
        id=id,
        publisher=publisher or PublisherId(random.randint(1, 1000)),
        title=NonEmptyStr(_faker.sentence()),
        corresponding_author=author(),
        authors=random_authorlist(),
        license=random_license(),
        publication_type=publication_type or UnknownConcept,
        subject_area=subject_area or UnknownConcept,
        open_access_type=random_open_access_type(),
        publication_state=Unpublished(),
        contracts=contracts,
        links={Doi("10.1234/5678")},
    )


def _random_date() -> date:
    return date.fromisoformat(_faker.date())


def payment() -> Payment:
    money = random_money()
    method = random.choice([m for m in PaymentMethod])
    return Payment(amount=money, method=method)


def random_money(currency: Currency | None = None) -> Money:
    amount = Decimal(random.random() * random.randint(1, 1000)).quantize(Decimal("0.01"))
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
) -> FundingRequest[Publication]:
    return FundingRequest(
        id=id or None,
        publication=publication(journal_id or JournalId(random.randint(1, 1000))),
        submitter=author(),
        estimated_cost=payment(),
        external_funding=[external_funding(funding_org_id)],
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


def random_role() -> Role:
    return random.choice([r for r in Role])


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
