import copy
import enum
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from django.db.models import F, Q, QuerySet
from django.db.models.functions import ExtractYear

from coda.apps.fundingrequests.mappers import FundingRequestListMapper
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.institutions.models import Institution
from coda.apps.search import words_icontains
from coda.domain.author import InstitutionId, Role
from coda.domain.date import DateRange
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication.publication import License, OpenAccessType

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
        if not self.search_term.strip():
            return Q()

        return words_icontains(
            self.search_term,
            "publication__title",
            "publication__relevant_authors__name",
            "publication__article_journal__title",
            "publication__article_journal__publisher__name",
            "publication__monograph_publisher__name",
            "request_id",
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


_CORRESPONDING_AUTHOR_ROLES = [
    Role.CORRESPONDING_AUTHOR.name,
    Role.SUBMITTING_CORRESPONDING_AUTHOR.name,
]


def _institution_subtree_pks(institutions: Iterable[InstitutionId]) -> list[int]:
    """Every persisted pk covered by the selection: each node and its whole subtree.

    Walks ``Institution.all_objects``, so archived nodes are included (Q19: the
    filter expands to the subtree, grouping on the statistics page does not).
    """
    pks: set[int] = set()
    for node in Institution.all_objects.filter(pk__in=institutions):
        pks.update(subtree_node.pk for subtree_node in node.walk())

    return sorted(pks)


@dataclass
class InstitutionCriteria:
    """Requests whose publication has a corresponding author affiliated with one
    of the selected institutions or any of their descendants (ADR-0006)."""

    institutions: list[InstitutionId] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.institutions:
            return Q()

        return Q(
            publication__relevant_authors__roles__in=_CORRESPONDING_AUTHOR_ROLES,
            publication__relevant_authors__affiliation__in=_institution_subtree_pks(
                self.institutions
            ),
        )


@dataclass
class PublisherCriteria:
    """Requests published by one of the selected publishers: either as the
    publisher of the article's journal or as the monograph publisher."""

    publishers: list[int] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.publishers:
            return Q()

        return Q(publication__article_journal__publisher__in=self.publishers) | Q(
            publication__monograph_publisher__in=self.publishers
        )


@dataclass
class JournalCriteria:
    """Requests whose article was published in one of the selected journals."""

    journals: list[int] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.journals:
            return Q()

        return Q(publication__article_journal__in=self.journals)


@dataclass
class FunderCriteria:
    """Requests that received external funding from one of the selected funders."""

    funders: list[int] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.funders:
            return Q()

        return Q(external_funding__organization__in=self.funders)


@dataclass
class SubjectAreaCriteria:
    """Requests whose publication carries one of the selected subject-area
    concepts, identified by the concept's entity id."""

    subject_areas: list[uuid.UUID] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.subject_areas:
            return Q()

        return Q(publication__subject_area__entity_id__in=self.subject_areas)


@dataclass
class PublicationTypeConceptCriteria:
    """Requests whose publication carries one of the selected publication-type
    concepts, identified by the concept's entity id."""

    publication_type_concepts: list[uuid.UUID] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.publication_type_concepts:
            return Q()

        return Q(publication__publication_type__entity_id__in=self.publication_type_concepts)


@dataclass
class LicenseCriteria:
    """Requests whose publication is published under one of the selected licenses."""

    licenses: list[License] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.licenses:
            return Q()

        license_names = [license.name for license in self.licenses]
        return Q(publication__license__in=license_names)


class PublicationForm(enum.StrEnum):
    article = "article"
    monograph = "monograph"


@dataclass
class PublicationFormCriteria:
    """Article vs monograph, decided by exactly one rule:

    a publication is an ``article`` when it has an ``article_journal`` and a
    ``monograph`` when it has a ``monograph_publisher``. The statistics dataset
    (``dataset.build_facts``) must derive ``RequestFact.publication_form`` from
    this same rule, or the facet and the chart disagree (spec §8). A
    publication with neither field matches neither form; with both, both.
    """

    publication_form: PublicationForm = PublicationForm.article

    def _to_query(self) -> Q:
        match self.publication_form:
            case PublicationForm.article:
                return Q(publication__article_journal__isnull=False)
            case PublicationForm.monograph:
                return Q(publication__monograph_publisher__isnull=False)


@dataclass
class CostTypeCriteria:
    """Requests that have a publication-scoped position with one of the selected
    cost types (§5 scoping: one invoice may cover several publications)."""

    cost_types: list[PublicationCostType] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.cost_types:
            return Q()

        values = [cost_type.value for cost_type in self.cost_types]
        return Q(publication__position__cost_type__in=values)


@dataclass
class FundingSourcesCriteria:
    """Requests whose publication positions have a cost-splitting assignment to
    one of the selected funding sources.

    "Unassigned" money is an arithmetic remainder, not an assignment row, so it
    is deliberately not a filterable value (spec §8).
    """

    funding_sources: list[FundingSourceId] = field(default_factory=list)

    def _to_query(self) -> Q:
        if not self.funding_sources:
            return Q()

        return Q(
            publication__position__funding_assignments__funding_source__in=self.funding_sources
        )


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
    institutions: list[InstitutionId] | None = None
    publishers: list[int] | None = None
    journals: list[int] | None = None
    funders: list[int] | None = None
    subject_areas: list[uuid.UUID] | None = None
    publication_type_concepts: list[uuid.UUID] | None = None
    licenses: list[License] | None = None
    publication_form: PublicationForm | None = None
    cost_types: list[PublicationCostType] | None = None
    funding_sources: list[FundingSourceId] | None = None
    decimal_separator: str = "."

    def without_date_range(self) -> "FundingRequestSearchParams":
        # return a new instance with the date_range set to None, keeping all other attributes the same
        new_instance = copy.copy(
            self
        )  # shallow copy is sufficient since all attributes are immutable or primitive
        new_instance.date_range = None
        return new_instance


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
        _institution_criterion(params),
        _publisher_criterion(params),
        _journal_criterion(params),
        _funder_criterion(params),
        _subject_area_criterion(params),
        _publication_type_concept_criterion(params),
        _license_criterion(params),
        _publication_form_criterion(params),
        _cost_type_criterion(params),
        _funding_sources_criterion(params),
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


def _institution_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return InstitutionCriteria(institutions=params.institutions) if params.institutions else None


def _publisher_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return PublisherCriteria(publishers=params.publishers) if params.publishers else None


def _journal_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return JournalCriteria(journals=params.journals) if params.journals else None


def _funder_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return FunderCriteria(funders=params.funders) if params.funders else None


def _subject_area_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return SubjectAreaCriteria(subject_areas=params.subject_areas) if params.subject_areas else None


def _publication_type_concept_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    if not params.publication_type_concepts:
        return None
    return PublicationTypeConceptCriteria(
        publication_type_concepts=params.publication_type_concepts
    )


def _license_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return LicenseCriteria(licenses=params.licenses) if params.licenses else None


def _publication_form_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        PublicationFormCriteria(publication_form=params.publication_form)
        if params.publication_form
        else None
    )


def _cost_type_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return CostTypeCriteria(cost_types=params.cost_types) if params.cost_types else None


def _funding_sources_criterion(
    params: FundingRequestSearchParams,
) -> FundingRequestSearchCriteria | None:
    return (
        FundingSourcesCriteria(funding_sources=params.funding_sources)
        if params.funding_sources
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
