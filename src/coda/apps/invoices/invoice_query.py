import abc
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import singledispatch
from typing import TypeVar

from django.db.models import Case, DecimalField, Exists, F, OuterRef, Q, QuerySet, Sum, Value, When
from django.db.models.functions import Coalesce, ExtractYear

from coda.apps.invoices.mappers._list import InvoiceListMapper
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId, PaymentStatus
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Currency

T = TypeVar("T")


def empty_if_none(crit: Callable[[T], Q]) -> Callable[[T | None], Q]:
    def _wrapped(value: T | None) -> Q:
        if value is None:
            return Q()
        return crit(value)

    return _wrapped


class UnsupportedCriterion(TypeError):
    pass


@dataclass(frozen=True)
class InvoiceSearchCriterion(abc.ABC):
    pass


@singledispatch
def to_query(criterion: InvoiceSearchCriterion) -> Q:
    raise UnsupportedCriterion(criterion.__class__.__name__)


@dataclass(frozen=True)
class GenericSearchCriterion(InvoiceSearchCriterion):
    generic_search: str


@empty_if_none
@to_query.register
def generic_search_criterion(criterion: GenericSearchCriterion) -> Q:
    return (
        _invoice_number_criterion(criterion.generic_search)
        | _creditor_criterion(criterion.generic_search)
        | Q(positions__publication__fundingrequest__request_id__iexact=criterion.generic_search)
        | Q(external_invoice_id__iexact=criterion.generic_search)
    )


@empty_if_none
def _invoice_number_criterion(invoice_number: str) -> Q:
    return Q(number__icontains=invoice_number)


@empty_if_none
def _creditor_criterion(creditor: str) -> Q:
    return Q(creditor__name__icontains=creditor)


@dataclass(frozen=True)
class PaymentStatusCriterion(InvoiceSearchCriterion):
    payment_status: PaymentStatus


@empty_if_none
@to_query.register
def status_criterion(criterion: PaymentStatusCriterion) -> Q:
    return Q(status=criterion.payment_status.value)


@dataclass(frozen=True)
class DateRangeCriterion(InvoiceSearchCriterion):
    date_range: DateRange


@empty_if_none
@to_query.register
def date_range_criterion(criterion: DateRangeCriterion) -> Q:
    return Q(date__range=(criterion.date_range.start, criterion.date_range.end))


@dataclass(frozen=True)
class FundingSourceCriterion(InvoiceSearchCriterion):
    funding_source: FundingSourceId


@empty_if_none
@to_query.register
def funding_source_criterion(criterion: FundingSourceCriterion) -> Q:
    return Q(positions__funding_assignments__funding_source__exact=criterion.funding_source)


@dataclass(frozen=True)
class MissingExternalIdCriterion(InvoiceSearchCriterion):
    pass


@to_query.register
def missing_external_id_criterion(criterion: MissingExternalIdCriterion) -> Q:
    return Q(external_invoice_id__isnull=True) | Q(external_invoice_id__exact="")


@dataclass(frozen=True)
class MissingCurrencyConversionCriterion(InvoiceSearchCriterion):
    home_currency: Currency


@empty_if_none
@to_query.register
def missing_currency_conversion_criterion(criterion: MissingCurrencyConversionCriterion) -> Q:
    return (
        Q(positions__cost_currency__isnull=False)
        & ~Q(positions__cost_currency=criterion.home_currency.code)
        & Q(currency_conversions__isnull=True)
    )


@dataclass(frozen=True)
class ContractCriterion(InvoiceSearchCriterion):
    contract_id: str | int
    positions_only: bool = False


@to_query.register
def contract_criterion(criterion: ContractCriterion) -> Q:
    query = Q(positions__contract_id=criterion.contract_id)
    if not criterion.positions_only:
        query |= Q(positions__publication__attached_contracts__contract_id=criterion.contract_id)
    return query


@dataclass(frozen=True)
class ContractYearCriterion(InvoiceSearchCriterion):
    contract_year: str | int
    contract_positions_only: bool = False


@empty_if_none
@to_query.register
def contract_year_criterion(criterion: ContractYearCriterion) -> Q:
    query = Q(positions__contract_year=criterion.contract_year)
    if not criterion.contract_positions_only:
        query |= Q(
            positions__publication__attached_contracts__contract_year=criterion.contract_year
        )
    return query


def _invalid_contract_year_filter() -> Q:
    """
    Returns a Q object that matches positions with invalid contract years.

    A contract year is invalid if the year falls outside the contract's active period:
    - contract_year < YEAR(contract.start_date) OR
    - contract_year > YEAR(contract.end_date)

    This logic is shared between the annotation (for display) and the filter criterion.
    """
    return Q(
        contract__isnull=False,
        contract_year__isnull=False,
    ) & (
        Q(contract_year__lt=ExtractYear(F("contract__start_date")))
        | Q(contract_year__gt=ExtractYear(F("contract__end_date")))
    )


@dataclass(frozen=True)
class HasErrorsCriterion(InvoiceSearchCriterion):
    pass


@to_query.register
def has_errors_criterion(criterion: HasErrorsCriterion) -> Q:
    """
    Filter for invoices with errors.

    Currently checks for:
    - Invalid contract years (contract years outside the contract's active period)
    """
    return Q(
        Exists(
            PositionModel.objects.filter(invoice_id=OuterRef("pk")).filter(
                _invalid_contract_year_filter()
            )
        )
    )


def search(
    *criteria: InvoiceSearchCriterion, sort_by: str = "date_desc"
) -> Sequence[InvoiceListItem]:
    query = Q()
    for c in criteria:
        query &= to_query(c)

    qs = InvoiceModel.objects.filter(query).distinct()

    list_items = get_sorted_list_items(qs, sort_by)

    return list_items


def get_sorted_list_items(qs: QuerySet[InvoiceModel], sort_by: str) -> Sequence[InvoiceListItem]:
    sort_functions = {
        "alphabetical": _ordered_alphabetically,
        "date_asc": _ordered_date_asc,
        "date_desc": _ordered_date_desc,
    }
    sort_function = sort_functions.get(sort_by, _ordered_date_desc)
    qs = _annotate_position_based_data(InvoiceListMapper.prefetch(sort_function(qs)))
    return [
        InvoiceListMapper.map(
            model,
            net_total=getattr(model, "net_total"),
            tax_total=getattr(model, "tax_total"),
            first_position_currency=getattr(model, "first_position_currency"),
            has_invalid_contract_years=getattr(model, "has_invalid_contract_years"),
        )
        for model in qs
    ]


def _annotate_position_based_data(qs: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return qs.annotate(
        net_total=Coalesce(
            Sum(
                Case(
                    When(positions__cost_type="vat", then=Value(0)),
                    default=F("positions__cost_amount"),
                    output_field=DecimalField(),
                )
            ),
            Decimal("0"),
        ),
        tax_total=Coalesce(
            Sum(
                Case(
                    When(positions__cost_type="vat", then=F("positions__cost_amount")),
                    default=F("positions__cost_amount") * F("positions__tax_rate"),
                    output_field=DecimalField(),
                )
            ),
            Decimal("0"),
        ),
        first_position_currency=Coalesce("positions__cost_currency", Value("EUR")),
        has_invalid_contract_years=Exists(
            PositionModel.objects.filter(invoice_id=OuterRef("pk")).filter(
                _invalid_contract_year_filter()
            )
        ),
    )


def _ordered_alphabetically(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("number")


def _ordered_date_asc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("date")


def _ordered_date_desc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("-date")


def build_invoice_query(*criteria: InvoiceSearchCriterion) -> QuerySet[InvoiceModel]:
    query = Q()
    for c in criteria:
        query &= to_query(c)
    return InvoiceModel.objects.filter(query).distinct()
