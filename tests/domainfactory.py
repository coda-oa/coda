import random
from datetime import date
from decimal import Decimal
from typing import cast

import faker

from coda.domain import orcid
from coda.domain.author import Author, AuthorId, AuthorNames, InstitutionId, Role
from coda.domain.contract import Contract, ContractId, ContractYear, PublisherId
from coda.domain.date import DateRange
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget, SplitSource
from coda.domain.finance.invoice import (
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    PaymentStatus,
    Positions,
)
from coda.domain.finance.invoice_positions import ContractItem, FreeItem, Position, PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
    PaymentMethod,
    Review,
)
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    JournalId,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
)
from coda.domain.publication.links import Doi, Isbn
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept

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

    return Author.restore(
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
    positions: Positions | None = None,
) -> Invoice:
    status = random.choice([s for s in PaymentStatus])
    return Invoice(
        id=id,
        date=date.fromisoformat(_faker.date()),
        number=NonEmptyStr(str(_faker.uuid4())),
        creditor=creditor or CreditorId(random.randint(1, 1000)),
        positions=(
            positions
            if positions is not None
            else [
                publication_position(),
                free_position(),
                contract_position(contract_year(contract())),
            ]
        ),
        status=status,
        external_invoice_id=str(_faker.uuid4()),
        comment=_faker.sentence(),
    )


def publication_position(
    publication: PublicationId | None = None,
    currency: Currency | None = None,
    cost_type: PublicationCostType | None = None,
) -> Position:
    return invoice_positions.create(
        item=PublicationItem(
            publication or PublicationId(random.randint(1, 1000)),
            cost_type=cost_type or random.choice(list(PublicationCostType)),
        ),
        cost=random_money(currency),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
        external_position_id=str(_faker.uuid4()),
    )


def contract_position(
    contract: ContractYear,
    currency: Currency | None = None,
    cost_type: ContractCostType | None = None,
) -> Position:
    return invoice_positions.create(
        item=ContractItem(
            contract,
            cost_type=cost_type or random.choice(list(ContractCostType)),
        ),
        cost=random_money(currency),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
        external_position_id=str(_faker.uuid4()),
    )


def free_position(
    currency: Currency | None = None, cost_type: PublicationCostType | None = None
) -> Position:
    return invoice_positions.create(
        item=FreeItem(
            _faker.sentence(),
            cost_type=cost_type or random.choice(list(PublicationCostType)),
        ),
        cost=random_money(currency),
        tax_rate=TaxRate(_faker.pydecimal(positive=True, max_value=1)),
        external_position_id=str(_faker.uuid4()),
    )


def budget(id: FundingSourceId | None = None) -> Budget:
    return Budget(id, _faker.company())


def split_source(institution: InstitutionId | None = None, name: str = "") -> SplitSource:
    return SplitSource.new(
        institution or InstitutionId(_faker.random_int(min=1)), name or _faker.company()
    )


def publication(
    journal: JournalId | None = None,
    title: str = "",
    relevant_authors: Authors | None = None,
    publication_type: VocabularyConcept | None = None,
    subject_area: VocabularyConcept | None = None,
    contracts: tuple[ContractYear, ...] = (),
    *,
    id: PublicationId | None = None,
) -> Publication:
    return Publication(
        id=id,
        title=NonEmptyStr(title or _faker.sentence()),
        journal=journal or JournalId(random.randint(1, 1000)),
        relevant_authors=relevant_authors if relevant_authors is not None else _relevant_authors(),
        other_authors=random_authorlist(),
        license=random_license(),
        publication_type=publication_type or UnknownConcept,
        subject_area=subject_area or UnknownConcept,
        open_access_type=random_open_access_type(),
        publication_state=random_publication_status(),
        contracts=contracts,
        links=publication_links(),
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
        relevant_authors=_relevant_authors(),
        other_authors=random_authorlist(),
        license=random_license(),
        publication_type=publication_type or UnknownConcept,
        subject_area=subject_area or UnknownConcept,
        open_access_type=random_open_access_type(),
        publication_state=random_publication_status(),
        contracts=contracts,
        links=publication_links(),
    )


def publication_links() -> set[Link]:
    return {Doi("10.1234/5678"), Isbn("9783608961157")}


def random_publication_status() -> PublicationState:
    return cast(
        PublicationState, random.choice([Unpublished(), Published(_random_date(), _random_date())])
    )


def _random_date() -> date:
    return date.fromisoformat(_faker.date())


def _relevant_authors() -> Authors:
    return Authors(
        (
            author(role=Role.SUBMITTING_CORRESPONDING_AUTHOR),
            *(author(role=NoRole) for _ in range(random.randint(1, 3))),
        )
    )


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


def fundingrequest_contact() -> FilledContact:
    return FilledContact(
        name=NonEmptyStr(_faker.name()),
        email=_faker.email(),
    )


def fundingrequest(
    *,
    id: FundingRequestId | None = None,
    request_id: PublicFundingRequestId | None = None,
    journal_id: JournalId | None = None,
    funding_org_id: FundingOrganizationId | None = None,
    review: Review | None = None,
) -> FundingRequest[Publication]:
    return FundingRequest(
        id=id or None,
        request_id=request_id or PublicFundingRequestId.create(),
        publication=publication(journal_id or JournalId(random.randint(1, 1000))),
        extra_contact=fundingrequest_contact(),
        estimated_cost=payment(),
        external_funding=[external_funding(funding_org_id)],
        request_remarks=_faker.sentence(),
        review=review,
    )


def random_authorlist() -> AuthorNames:
    return AuthorNames(_faker.name() for _ in range(random.randint(1, 5)))


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
