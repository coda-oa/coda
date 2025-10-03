import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db.models import Q

from coda.apps.fundingrequests.models import FundingRequest
from coda.domain.date import DateRange
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
        effective_labels = set(self.include_labels) - set(self.exclude_labels)
        if not effective_labels:
            return Q()

        return Q(labels__in=effective_labels)


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


@dataclass
class FundingRequestSearchCriteria:
    generic_search: GenericSearchCriteria = field(default_factory=GenericSearchCriteria)
    review_results: ReviewResultCriteria = field(default_factory=ReviewResultCriteria)
    open_access_types: OpenAccessTypeCriteria = field(default_factory=OpenAccessTypeCriteria)
    date_range: DateRangeCriteria = field(default_factory=DateRangeCriteria)
    payment_statuses: PaymentStatusCriteria = field(default_factory=PaymentStatusCriteria)
    labels: LabelsSearchCriteria = field(default_factory=LabelsSearchCriteria)
    contract: ContractSearchCriteria = field(default_factory=ContractSearchCriteria)

    def _to_query(self) -> Q:
        return (
            self.generic_search._to_query()
            & self.review_results._to_query()
            & self.open_access_types._to_query()
            & self.date_range._to_query()
            & self.payment_statuses._to_query()
            & self.labels._to_query()
            & self.contract._to_query()
        )


def search(
    criteria: FundingRequestSearchCriteria,
    sort_order: SortOrder = SortOrder.default(),
) -> Iterable[FundingRequest]:
    return (
        FundingRequest.objects.filter(criteria._to_query())
        .distinct()
        .select_related(
            "review",
            "publication__article_journal",
            "publication__monograph_publisher",
        )
        .prefetch_related(
            "labels",
            "publication__relevant_authors",
        )
        .order_by(sort_order)
    )
