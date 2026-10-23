# tests/reporting/helpers.py

import uuid
from datetime import date
from decimal import Decimal

from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices import funding_source_repository
from coda.apps.publications.models import (
    AttachedContract,
    PublicationAttachedConcept,
)
from coda.apps.reporting import dataset, queries
from coda.contexts.finance.services import invoice_service
from coda.contexts.statistics.dto import RequestFact
from coda.domain.author import Role
from coda.domain.date import DateRange
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import Position, PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors
from coda.domain.publication.publication import PublicationId
from tests import modelfactory

PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)


def facts(*, report_currency: Currency = Currency.EUR) -> tuple[RequestFact, ...]:
    """The whole statistics pipeline below the view: fetch_requests -> build_facts."""
    return dataset.build_facts(queries.fetch_requests(criteria()), report_currency)


def criteria() -> list[fundingrequest_query.FundingRequestSearchCriteria]:
    return fundingrequest_query.build_criteria(
        fundingrequest_query.FundingRequestSearchParams(
            date_range=DateRange(PERIOD_START, PERIOD_END),
        )
    )


def request(title: str, authors: Authors | None = None) -> FundingRequest:
    fr = modelfactory.fundingrequest(title=title, authors=authors)
    fr.request_date = date(2026, 3, 15)
    fr.save()
    return fr


def corresponding_author(fr: FundingRequest, institution_id: int) -> None:
    author = modelfactory.author()
    author.publication = fr.publication
    author.roles = Role.CORRESPONDING_AUTHOR.name
    author.affiliation_id = institution_id
    author.save()


def with_concepts(fr: FundingRequest) -> None:
    vocabulary = modelfactory.vocabulary()
    subject_area = modelfactory.concept(vocabulary=vocabulary)
    publication_type = modelfactory.concept(vocabulary=vocabulary)
    fr.publication.subject_area = PublicationAttachedConcept.objects.create(
        name=subject_area.name,
        vocabulary=vocabulary,
        entity_id=subject_area.entity_id,
    )
    fr.publication.publication_type = PublicationAttachedConcept.objects.create(
        name=publication_type.name,
        vocabulary=vocabulary,
        entity_id=publication_type.entity_id,
    )
    fr.publication.save()


def with_attached_contract(fr: FundingRequest) -> None:
    AttachedContract.objects.create(
        contract=modelfactory.contract(),
        contract_year=2024,
        publication=fr.publication,
    )


def position(
    publication_id: int,
    amount: Decimal,
    tax_rate: Decimal,
    cost_type: str = "gold-oa",
    currency: Currency = Currency.EUR,
) -> Position:
    return invoice_positions.create(
        item=PublicationItem(PublicationId(publication_id), PublicationCostType(cost_type)),
        cost=Money(amount, currency),
        tax_rate=TaxRate(tax_rate),
        external_position_id="",
    )


def budget(name: str) -> Budget:
    source = Budget(None, name)
    source.id = funding_source_repository.create(source)
    return source


# Statistics fixtures keep invoices unpaid: the domain refuses to save a
# paid invoice whose costs are not fully assigned, and part of what the
# dataset must handle is partially assigned positions (§5 remainder).


def invoice(
    positions: list[Position],
    conversions: dict[Currency, Decimal] | None = None,
) -> int:
    """Save an invoice over the given positions; returns its pk."""
    creditor = modelfactory.creditor()
    saved = Invoice.new(
        number=uuid.uuid4().hex,
        date=date(2026, 3, 20),
        creditor=CreditorId(creditor.pk),
        positions=positions,
    )
    for currency, rate in (conversions or {}).items():
        saved.add_conversion(rate, currency)
    saved.id = invoice_service.save(saved)
    return saved.id
