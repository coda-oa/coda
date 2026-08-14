import abc
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import singledispatch
from typing import TypeVar

from django.db.models import Case, DecimalField, Exists, F, OuterRef, Q, QuerySet, Sum, Value, When
from django.db.models.functions import Coalesce, ExtractYear

from coda.apps.invoices.mappers._list import InvoiceListMapper
from coda.apps.search import build_search_filter
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
    if not criterion.generic_search.strip():
        return Q()
    return build_search_filter(
        criterion.generic_search,
        "number",
        "creditor__name",
        "external_invoice_id",
        "positions__publication__fundingrequest__request_id",
    )


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


@dataclass
class InvoiceSearchParams:
    date_range: DateRange | None = None
    payment_status: PaymentStatus | None = None
    search_term: str = ""
    funding_source: FundingSourceId | None = None
    contract_id: str | int | None = None
    contract_positions_only: bool = False
    contract_year: str | int | None = None
    contract_year_positions_only: bool = False
    has_external_id: bool | None = None
    has_foreign_currency: bool = False
    home_currency: Currency | None = None
    has_errors: bool = False


def build_criteria(params: InvoiceSearchParams) -> list[InvoiceSearchCriterion]:
    criteria = (
        _date_range_criterion(params),
        _payment_status_criterion(params),
        _search_term_criterion(params),
        _funding_source_criterion(params),
        _contract_criterion(params),
        _contract_year_criterion(params),
        _missing_external_id_criterion(params),
        _missing_currency_conversion_criterion(params),
        _has_errors_criterion(params),
    )
    return [c for c in criteria if c is not None]


def _date_range_criterion(params: InvoiceSearchParams) -> DateRangeCriterion | None:
    return DateRangeCriterion(params.date_range) if params.date_range is not None else None


def _payment_status_criterion(params: InvoiceSearchParams) -> PaymentStatusCriterion | None:
    return (
        PaymentStatusCriterion(params.payment_status) if params.payment_status is not None else None
    )


def _search_term_criterion(params: InvoiceSearchParams) -> GenericSearchCriterion | None:
    return GenericSearchCriterion(params.search_term) if params.search_term else None


def _funding_source_criterion(params: InvoiceSearchParams) -> FundingSourceCriterion | None:
    return (
        FundingSourceCriterion(params.funding_source) if params.funding_source is not None else None
    )


def _contract_criterion(params: InvoiceSearchParams) -> ContractCriterion | None:
    if params.contract_id is None:
        return None
    return ContractCriterion(
        contract_id=params.contract_id, positions_only=params.contract_positions_only
    )


def _contract_year_criterion(params: InvoiceSearchParams) -> ContractYearCriterion | None:
    if params.contract_year is None:
        return None
    return ContractYearCriterion(
        contract_year=params.contract_year,
        contract_positions_only=params.contract_year_positions_only,
    )


def _missing_external_id_criterion(
    params: InvoiceSearchParams,
) -> MissingExternalIdCriterion | None:
    return MissingExternalIdCriterion() if params.has_external_id is False else None


def _missing_currency_conversion_criterion(
    params: InvoiceSearchParams,
) -> MissingCurrencyConversionCriterion | None:
    if not params.has_foreign_currency:
        return None
    home_currency = params.home_currency or Currency.EUR
    return MissingCurrencyConversionCriterion(home_currency)


def _has_errors_criterion(params: InvoiceSearchParams) -> HasErrorsCriterion | None:
    return HasErrorsCriterion() if params.has_errors else None


def search(*criteria: InvoiceSearchCriterion) -> QuerySet[InvoiceModel]:
    query = Q()
    for c in criteria:
        query &= to_query(c)
    return InvoiceModel.objects.filter(query).distinct()


def search_to_list_items(
    *criteria: InvoiceSearchCriterion, sort_by: str = "date_desc"
) -> Sequence[InvoiceListItem]:
    sort_functions = {
        "alphabetical": _ordered_alphabetically,
        "date_asc": _ordered_date_asc,
        "date_desc": _ordered_date_desc,
    }
    sort_function = sort_functions.get(sort_by, _ordered_date_desc)
    qs = _annotate_position_based_data(InvoiceListMapper.prefetch(sort_function(search(*criteria))))
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
