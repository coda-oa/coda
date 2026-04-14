import datetime
import enum
from dataclasses import dataclass, field
from typing import Protocol

from django.db.models import F, Prefetch, Q, QuerySet
from django.db.models.functions import ExtractYear

from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.domain.date import DateRange
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


@dataclass
class DateRangeCriteria:
    start: datetime.date | str | None = None
    end: datetime.date | str | None = None

    def _to_query(self) -> Q:
        start: datetime.date | None
        end: datetime.date | None
        if isinstance(self.start, str) and self.start:
            start = datetime.date.fromisoformat(self.start)
        else:
            start = self.start or None

        if isinstance(self.end, str) and self.end:
            end = datetime.date.fromisoformat(self.end)
        else:
            end = self.end or None

        date_range = DateRange.create(start=start, end=end)
        if date_range.is_unbounded():
            return Q()

        return Q(request_date__gte=date_range.start, request_date__lte=date_range.end)


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
    return (
        FundingRequest.objects.filter(_to_query(*criteria))
        .distinct()
        .select_related(
            "review",
            "publication__article_journal",
            "publication__monograph_publisher",
        )
        .prefetch_related(
            Prefetch("labels", queryset=Label.objects.order_by("name")),
            "publication__relevant_authors",
            "publication__attached_contracts__contract",
        )
        .order_by(sort_order)
    )
