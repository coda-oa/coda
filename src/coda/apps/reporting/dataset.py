"""ORM rows -> RequestFact values (plan §5, §10).

The gross money rules delegate to ``contexts/statistics/measures``; currency
is applied here, per position, with the rate recorded on the position's
invoice (ADR-0003). Amounts without a rate are excluded and counted, never
silently dropped.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from coda.apps.fundingrequests.fundingrequest_query import PublicationForm
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.mappers._domain import FundingSourceDomainMapper
from coda.apps.invoices.models import Invoice, Position
from coda.apps.publications.models import Publication
from coda.contexts.statistics.dimensions import FORM_UNKNOWN
from coda.contexts.statistics.dto import (
    ContractRef,
    FundingSourceRef,
    InstitutionRef,
    RequestFact,
)
from coda.contexts.statistics.measures import (
    gross_assignment,
    gross_of,
    is_vat_cost_type,
)
from coda.domain.author import Role
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, CurrencyExchange, Money

ZERO = Decimal("0.00")

CORRESPONDING_AUTHOR_ROLES = frozenset(
    {Role.CORRESPONDING_AUTHOR.name, Role.SUBMITTING_CORRESPONDING_AUTHOR.name}
)


def build_facts(
    requests: Iterable[FundingRequest], report_currency: Currency
) -> tuple[RequestFact, ...]:
    """Turn the fetched requests into the fact set the pure layer aggregates."""
    return tuple(_build_fact(request, report_currency) for request in requests)


def publication_form(publication: Publication) -> str:
    """Article iff ``article_journal``, monograph iff ``monograph_publisher``,
    neither -> the ``FORM_UNKNOWN`` sentinel — the single rule shared with
    ``PublicationFormCriteria`` (plan §8, §2 #7). Both fields set: both facet
    values match it and the single-valued fact takes article first; neither
    set: no facet value matches, so the fact claims no form and the chart
    groups it with the other linkless "Unknown" rows."""
    if publication.article_journal_id:
        return PublicationForm.article
    if publication.monograph_publisher_id:
        return PublicationForm.monograph
    return FORM_UNKNOWN


def _build_fact(request: FundingRequest, report_currency: Currency) -> RequestFact:
    publication = request.publication
    money = _money_of(request, report_currency)
    corresponding_authors = sorted(
        (
            author
            for author in publication.relevant_authors.all()
            if author.roles in CORRESPONDING_AUTHOR_ROLES
        ),
        key=lambda author: author.pk,
    )
    return RequestFact(
        request_id=request.pk,
        publication_id=publication.pk,
        request_date=request.request_date,
        title=publication.title,
        subject_area=(publication.subject_area.name if publication.subject_area_id else None),
        publication_type=(
            publication.publication_type.name if publication.publication_type_id else None
        ),
        publication_form=publication_form(publication),
        license=publication.license,
        open_access_type=publication.open_access_type,
        journal=(journal.title if (journal := publication.article_journal) else None),
        publisher=_publisher_name(publication),
        contracts=_unique(
            ContractRef(
                pk=attached.contract.pk,
                name=attached.contract.name,
                year=attached.contract_year,
            )
            for attached in sorted(publication.attached_contracts.all(), key=lambda ac: ac.pk)
        ),
        funders=_unique(
            funding.organization.name
            for funding in sorted(request.external_funding.all(), key=lambda f: f.pk)
        ),
        institutions=_unique(
            InstitutionRef(author.affiliation.name)
            for author in corresponding_authors
            if author.affiliation is not None
        ),
        no_corresponding_author=not corresponding_authors,
        paid_out_by_cost_type=money.by_cost_type,
        paid_out_total=money.total,
        funded_by=money.funded_by,
        unassigned=money.unassigned,
        invoices_without_rate=money.invoices_without_rate,
        unconvertible_invoice_ids=money.unconvertible_invoice_ids,
        has_invoice=money.has_invoice,
    )


def _publisher_name(publication: Publication) -> str | None:
    if (journal := publication.article_journal) is not None:
        return journal.publisher.name
    if (monograph_publisher := publication.monograph_publisher) is not None:
        return monograph_publisher.name
    return None


@dataclass(slots=True)
class _Money:
    by_cost_type: dict[str, Decimal] = field(default_factory=dict)
    total: Decimal = ZERO
    funded_by: dict[FundingSourceRef, Decimal] = field(default_factory=dict)
    unassigned: Decimal = ZERO
    invoices_without_rate: int = 0
    unconvertible_invoice_ids: tuple[int, ...] = ()
    has_invoice: bool = False


def _money_of(request: FundingRequest, report_currency: Currency) -> _Money:
    """Gross amounts per request, converted per invoice (plan §5, §10).

    Only positions scoped to this request's publication are summed: one
    invoice can cover several publications, and contract or free positions
    carry no publication, so they cannot be attributed to a request (ADR-0005).
    Walking ``position_set`` enforces that scoping by construction.
    """
    money = _Money()
    unconvertible_invoices: set[int] = set()
    positions = sorted(request.publication.position_set.all(), key=lambda p: p.pk)
    for position in positions:
        money.has_invoice = True
        rate = _conversion_rate(position.invoice, Currency[position.cost_currency], report_currency)
        if rate is None:
            unconvertible_invoices.add(position.invoice_id)
            continue
        _add_position(money, position, report_currency, rate)
    money.invoices_without_rate = len(unconvertible_invoices)
    money.unconvertible_invoice_ids = tuple(sorted(unconvertible_invoices))
    return money


def _add_position(
    money: _Money,
    position: Position,
    report_currency: Currency,
    rate: Decimal,
) -> None:
    currency = Currency[position.cost_currency]
    tax_rate = TaxRate(position.tax_rate)
    is_vat = is_vat_cost_type(position.cost_type)
    exchange = _fixed_exchange(rate)
    gross = gross_of(Money(position.cost_amount, currency), tax_rate, is_vat=is_vat)
    converted = gross.convert_to(report_currency, exchange)
    money.total += converted.amount
    money.by_cost_type[position.cost_type] = (
        money.by_cost_type.get(position.cost_type, ZERO) + converted.amount
    )

    assigned = ZERO
    for assignment in sorted(position.funding_assignments.all(), key=lambda a: a.pk):
        if assignment.funding_source is None:
            continue  # a row without a source belongs to the remainder
        amount = gross_assignment(assignment.amount, tax_rate, currency, is_vat=is_vat).convert_to(
            report_currency, exchange
        )
        source = FundingSourceDomainMapper.map(assignment.funding_source)
        ref = FundingSourceRef(source.name)
        money.funded_by[ref] = money.funded_by.get(ref, ZERO) + amount.amount
        assigned += amount.amount

    money.unassigned += converted.amount - assigned


def _conversion_rate(
    invoice: Invoice, position_currency: Currency, report_currency: Currency
) -> Decimal | None:
    """The invoice's multiplier into the report currency, or None (ADR-0003).

    A position already in the report currency needs no rate; otherwise the
    invoice must carry a conversion whose target is the report currency.
    """
    if position_currency is report_currency:
        return Decimal(1)
    for conversion in invoice.currency_conversions.all():
        if conversion.target_currency == report_currency.code:
            return conversion.exchange_rate
    return None


def _fixed_exchange(rate: Decimal) -> CurrencyExchange:
    """Mirrors the domain's ``_internal_exchange``: the invoice rate is the
    multiplier from the invoice's home currency into its target."""

    def _exchange(origin: Currency, target: Currency) -> Decimal:
        return rate

    return _exchange


def _unique[T](values: Iterable[T]) -> tuple[T, ...]:
    """Distinct values, in order — a repeated dimension counts a request once
    per value, not once per author row (ADR-0007)."""
    return tuple(dict.fromkeys(values))
