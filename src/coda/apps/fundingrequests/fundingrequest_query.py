import enum
from dataclasses import dataclass, field
from typing import Protocol

from django.db.models import F, Q, QuerySet
from django.db.models.functions import ExtractYear

from coda.apps.fundingrequests.mappers import FundingRequestListMapper
from coda.apps.fundingrequests.models import FundingRequest
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication.publication import OpenAccessType

type LabelId = int
type ContractId = int


class PaymentStatus(enum.Enum):
    InvoiceReceived = "invoice_received"
    Paid = "paid"
    Unpaid = "unpaid"
    CoveredByContract = "covered_by_contract"

    def is_individual(self) -> bool:
        return self != PaymentStatus.CoveredByContract


_PAYMENT_STATUS_TO_QUERY = {
    PaymentStatus.InvoiceReceived: Q(publication__payments__status="invoice_received"),
    PaymentStatus.Paid: Q(publication__payments__status="paid"),
    PaymentStatus.Unpaid: Q(publication__payments__isnull=True)
    & ~Q(publication__attached_contracts__contract__publication_billing="consolidated"),
    PaymentStatus.CoveredByContract: Q(
        publication__attached_contracts__contract__publication_billing="consolidated"
    ),
}


@dataclass
class PaymentStatusCriteria:
    payment_statuses: list[PaymentStatus] = field(default_factory=list)

    def _to_query(self) -> Q:
        q = Q()

        for ps in self.payment_statuses:
            q |= _PAYMENT_STATUS_TO_QUERY[ps]

        return q


@dataclass
class LabelsSearchCriteria:
    include_labels: list[LabelId] = field(default_factory=list)
    exclude_labels: list[LabelId] = field(default_factory=list)

    def _to_query(self) -> Q:
        q = Q()

        if self.include_labels:
            q &= Q(labels__in=self.include_labels)
            q &= Q(labels__isnull=False)

        if self.exclude_labels:
            q &= ~Q(labels__in=self.exclude_labels)

        return q


@dataclass
class ContractSearchCriteria:
    contract: ContractId | None = None
    contract_year: int | None = None

    def _to_query(self) -> Q:
        q = Q()
        if self.contract:
            q &= Q(publication__attached_contracts__contract__id=self.contract)

        if self.contract_year:
            q &= Q(publication__attached_contracts__contract_year=self.contract_year)

        return q


class SortOrder(enum.StrEnum):
    alphabetical = "publication__title"
    date_asc = "request_date"
    date_desc = "-request_date"

    @staticmethod
    def default() -> "SortOrder":
        return SortOrder.date_desc

    @staticmethod
    def try_parse(value: str | None) -> "SortOrder":
        if not value:
            return SortOrder.default()

        try:
            return SortOrder[value]
        except KeyError:
            return SortOrder.default()


@dataclass
class ReviewResultCriteria:
    review_results: list[ReviewResult] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.review_results:
            return Q()

        review_states = [s.value.lower() for s in self.review_results]
        return Q(review__review_result__in=review_states)


@dataclass
class OpenAccessTypeCriteria:
    open_access_types: list[OpenAccessType] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.open_access_types:
            return Q()

        oa_types = [t.name for t in self.open_access_types]
        return Q(publication__open_access_type__in=oa_types)


@dataclass
class PublicationStateCriteria:
    publication_states: list[str] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.publication_states:
            return Q()

        return Q(publication__publication_state__in=self.publication_states)


@dataclass
class GenericSearchCriteria:
    search_term: str = ""

    def _to_query(self) -> Q:
        if not self.search_term:
            return Q()

        return (
            Q(publication__title__icontains=self.search_term)
            | Q(publication__relevant_authors__name__icontains=self.search_term)
            | Q(publication__article_journal__title__icontains=self.search_term)
            | Q(publication__article_journal__publisher__name__icontains=self.search_term)
            | Q(publication__monograph_publisher__name__icontains=self.search_term)
            | Q(request_id__icontains=self.search_term)
        )


@dataclass(frozen=True)
class DateRangeCriteria:
    date_range: DateRange

    def _to_query(self) -> Q:
        if self.date_range.is_unbounded():
            return Q()

        return Q(
            request_date__gte=self.date_range.start,
            request_date__lte=self.date_range.end,
        )


class PublicationEntityType(enum.Enum):
    All = "all"
    Article = "article"
    Monograph = "monograph"

    @classmethod
    def try_parse(cls, value: str | None) -> "PublicationEntityType":
        if value is None:
            return PublicationEntityType.All

        value = value.lower()
        try:
            return cls(value)
        except KeyError:
            return PublicationEntityType.All


@dataclass
class EntityTypeCriteria:
    entity_type: PublicationEntityType = PublicationEntityType.All

    def _to_query(self) -> Q:
        match self.entity_type:
            case PublicationEntityType.Article:
                return Q(publication__article_journal__isnull=False)
            case PublicationEntityType.Monograph:
                return Q(publication__monograph_publisher__isnull=False)
            case _:
                return Q()


@dataclass
class PaymentMethodCriteria:
    payment_methods: list[PaymentMethod] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.payment_methods:
            return Q()

        payment_methods = [method.value.lower() for method in self.payment_methods]
        return Q(payment_method__in=payment_methods)


@dataclass
class InvalidContractYearCriteria:
    """Filter for funding requests with invalid contract years.

    A contract year is invalid if it falls outside the contract's period:
    - contract_year < YEAR(contract.start_date) OR
    - contract_year > YEAR(contract.end_date)

    If ANY attached contract year is invalid, the funding request matches.
    """

    show_only_invalid: bool = False

    def _to_query(self) -> Q:
        if not self.show_only_invalid:
            return Q()

        return Q(
            Q(
                publication__attached_contracts__contract_year__lt=ExtractYear(
                    F("publication__attached_contracts__contract__start_date")
                )
            )
            | Q(
                publication__attached_contracts__contract_year__gt=ExtractYear(
                    F("publication__attached_contracts__contract__end_date")
                )
            )
        )


class FundingRequestSearchCriteria(Protocol):
    def _to_query(self) -> Q: ...


def _to_query(*criteria: FundingRequestSearchCriteria) -> Q:
    q = Q()
    for c in criteria:
        q &= c._to_query()

    return q


def search(
    *criteria: FundingRequestSearchCriteria,
    sort_order: SortOrder = SortOrder.default(),
) -> QuerySet[FundingRequest]:
    qs = FundingRequest.objects.filter(_to_query(*criteria)).distinct().order_by(sort_order)
    return FundingRequestListMapper.prefetch(qs)


@dataclass
class InvoiceFundingSourceCriteria:
    funding_source: FundingSourceId

    def _to_query(self) -> Q:
        return Q(publication__position__funding_assignments__funding_source=self.funding_source)


@dataclass
class FundingRequestSearchParams:
    date_range: DateRange | None = None
    review_results: list[ReviewResult] | None = None
    payment_statuses: list[PaymentStatus] | None = None
    labels: list[LabelId] | None = None
    exclude_labels: list[LabelId] | None = None
    payment_methods: list[PaymentMethod] | None = None
    open_access_types: list[OpenAccessType] | None = None
    publication_states: list[str] | None = None
    entity_type: PublicationEntityType = PublicationEntityType.All
    search_term: str = ""
    contract_id: ContractId | None = None
    contract_year: int | None = None
    show_invalid_contract_years: bool = False
    funding_source: FundingSourceId | None = None

    def without_date_range(self) -> "FundingRequestSearchParams":
        return FundingRequestSearchParams(
            date_range=None,
            review_results=self.review_results,
            payment_statuses=self.payment_statuses,
            labels=self.labels,
            exclude_labels=self.exclude_labels,
            payment_methods=self.payment_methods,
            open_access_types=self.open_access_types,
            publication_states=self.publication_states,
            entity_type=self.entity_type,
            search_term=self.search_term,
            contract_id=self.contract_id,
            contract_year=self.contract_year,
            show_invalid_contract_years=self.show_invalid_contract_years,
            funding_source=self.funding_source,
        )


def build_criteria(params: FundingRequestSearchParams) -> list[FundingRequestSearchCriteria]:
    criteria = (
        _date_range_criterion(params),
        _review_results_criterion(params),
        _payment_statuses_criterion(params),
        _labels_criterion(params),
        _payment_methods_criterion(params),
        _open_access_types_criterion(params),
        _publication_states_criterion(params),
        _entity_type_criterion(params),
        _search_term_criterion(params),
        _contract_criterion(params),
        _invalid_contract_year_criterion(params),
        _funding_source_criterion(params),
    )
    return [criterion for criterion in criteria if criterion is not None]


def _funding_source_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        InvoiceFundingSourceCriteria(funding_source=params.funding_source)
        if params.funding_source is not None
        else None
    )


def _invalid_contract_year_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        InvalidContractYearCriteria(show_only_invalid=True)
        if params.show_invalid_contract_years
        else None
    )


def _open_access_types_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        OpenAccessTypeCriteria(open_access_types=params.open_access_types)
        if params.open_access_types
        else None
    )


def _payment_methods_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        PaymentMethodCriteria(payment_methods=params.payment_methods)
        if params.payment_methods
        else None
    )


def _labels_criterion(params: FundingRequestSearchParams) -> FundingRequestSearchCriteria | None:
    return (
        LabelsSearchCriteria(
            include_labels=params.labels or [],
            exclude_labels=params.exclude_labels or [],
        )
        if params.labels or params.exclude_labels
        else None
    )


def _payment_statuses_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        PaymentStatusCriteria(payment_statuses=params.payment_statuses)
        if params.payment_statuses
        else None
    )


def _review_results_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        ReviewResultCriteria(review_results=params.review_results)
        if params.review_results
        else None
    )


def _date_range_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        DateRangeCriteria(date_range=params.date_range) if params.date_range is not None else None
    )


def _publication_states_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        PublicationStateCriteria(publication_states=params.publication_states)
        if params.publication_states
        else None
    )


def _entity_type_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        EntityTypeCriteria(entity_type=params.entity_type)
        if params.entity_type != PublicationEntityType.All
        else None
    )


def _search_term_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return GenericSearchCriteria(search_term=params.search_term) if params.search_term else None


def _contract_criterion(params: FundingRequestSearchParams) -> FundingRequestSearchCriteria | None:
    if params.contract_id is None and params.contract_year is None:
        return None

    return ContractSearchCriteria(
        contract=params.contract_id,
        contract_year=params.contract_year,
    )
