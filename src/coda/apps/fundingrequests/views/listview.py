import datetime
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest

from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.views.detailview import payment_status_viewmodel
from coda.apps.publications.services import publications
from coda.apps.views import EntityListView
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.payment import PublicationPaymentStatus
from coda.domain.publication.publication import PublicationId
from dataclasses import dataclass

from coda.apps.breadcrumbs.decorators import breadcrumb

_advanced_search_fields = [
    "labels",
    "exclude_labels",
    "processing_status",
    "open_access_type",
    "payment_status",
    "start_date",
    "end_date",
    "publication_type",
    "contract_name",
    "contract_year",
]

_payment_status_map = {
    "paid": fq.PaymentStatus.Paid,
    "unpaid": fq.PaymentStatus.Unpaid,
    "invoice_received": fq.PaymentStatus.InvoiceReceived,
    "covered_by_contract": fq.PaymentStatus.CoveredByContract,
}

_payment_status_choices = [
    ("paid", "Paid"),
    ("unpaid", "Unpaid"),
    ("invoice_received", "Invoice Received"),
    ("covered_by_contract", "Covered by Contract"),
]


@breadcrumb("Funding Requests", parent_url_name="fundingrequests:home")
class FundingRequestListView(LoginRequiredMixin, EntityListView["FundingRequestListViewModel"]):
    template_name = "fundingrequests/fundingrequest_list.html"
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"
    entity_filter_template = "fundingrequests/forms/fundingrequest_filter.html"

    def get_entities(self, request: HttpRequest) -> Sequence["FundingRequestListViewModel"]:
        fundingrequests = query(request)
        return DomainQuerySet(fundingrequests, as_viewmodel)  # type: ignore

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_contract_list_context())

        expand_advanced_search = any(self.request.GET.get(key) for key in _advanced_search_fields)

        labels = Label.objects.all()
        publication_types = [(et.value, et.value) for et in fq.PublicationEntityType]
        selected_publication_types = self.request.GET.get("publication_type")

        return ctx | {
            "labels": labels,
            "exlude_labels": labels,
            "processing_states": [rr.value for rr in ReviewResult],
            "open_access_types": [oat.value for oat in OpenAccessType],
            "expand_advanced_search": expand_advanced_search,
            "payment_status_choices": _payment_status_choices,
            "publication_types": publication_types,
            "selected_publication_types": selected_publication_types,
        }


fundingrequest_list = FundingRequestListView.as_view()


def query(request: HttpRequest) -> QuerySet[FundingRequestModel]:
    start_date = map_or_none(datetime.date.fromisoformat, request.GET.get("start_date"))
    end_date = map_or_none(datetime.date.fromisoformat, request.GET.get("end_date"))
    review_results = [ReviewResult(rr) for rr in request.GET.getlist("processing_status")]
    open_access_types = [OpenAccessType(oat) for oat in request.GET.getlist("open_access_type")]
    requested_payment_statuses = [
        _payment_status_map[status] for status in request.GET.getlist("payment_status")
    ]

    return cast(
        QuerySet[FundingRequestModel],
        fq.search(
            fq.GenericSearchCriteria(request.GET.get("search_term", "")),
            fq.ReviewResultCriteria(review_results),
            fq.EntityTypeCriteria(
                fq.PublicationEntityType.try_parse(request.GET.get("publication_type"))
            ),
            fq.OpenAccessTypeCriteria(open_access_types),
            fq.DateRangeCriteria(start_date, end_date),
            fq.PaymentStatusCriteria(requested_payment_statuses),
            fq.LabelsSearchCriteria(
                [int(_id) for _id in request.GET.getlist("labels")],
                [int(_id) for _id in request.GET.getlist("exclude_labels")],
            ),
            fq.ContractSearchCriteria(
                map_or_none(int, request.GET.get("contract_name")),
                map_or_none(int, request.GET.get("contract_year")),
            ),
            sort_order=fq.SortOrder.alphabetical,
        ),
    )


@dataclass(frozen=True)
class FundingRequestListViewModel:
    type: Literal["Article", "Monograph"]
    id: int | None
    url: str
    publication_title: str
    authors: list[str]
    publishing_entity_type: Literal["Journal", "Publisher"]
    publishing_entity_name: str
    publishing_entity_url: str
    updated_at: datetime.date
    labels: Iterable[Label]
    status: str
    payment_status: dict[str, Any] | None = None
    journal_publisher_name: str | None = None
    journal_publisher_url: str | None = None


def map_or_none[T](map_fn: Callable[[str], T], value: str | None) -> T | None:
    if value:
        return map_fn(value)

    return None


GetPaymentStatus = Callable[[PublicationId], PublicationPaymentStatus]


def as_viewmodel(
    funding_request: FundingRequestModel,
    get_payment_status: GetPaymentStatus = publications.get_payment_status,
) -> FundingRequestListViewModel:
    payment_status = get_payment_status(PublicationId(funding_request.publication.id))
    if is_article(funding_request):
        return article_viewmodel(funding_request, payment_status)
    elif is_monograph(funding_request):
        return monograph_viewmodel(funding_request, payment_status)

    raise ValueError("Funding request is neither an article nor a monograph.")


def article_viewmodel(
    funding_request: FundingRequestModel, payment_status: PublicationPaymentStatus
) -> FundingRequestListViewModel:
    assert funding_request.publication.article_journal is not None
    assert funding_request.review is not None

    journal = funding_request.publication.article_journal
    assert journal is not None

    journal_title = journal.title
    journal_url = journal.get_absolute_url()
    journal_publisher = str(journal.publisher) if journal.publisher else None
    journal_publisher_url = journal.publisher.get_absolute_url() if journal.publisher else None

    return FundingRequestListViewModel(
        type="Article",
        id=funding_request.id,
        url=funding_request.get_absolute_url(),
        publication_title=funding_request.publication.title,
        authors=[author.name for author in funding_request.publication.relevant_authors.all()],
        publishing_entity_type="Journal",
        publishing_entity_name=journal_title,
        publishing_entity_url=journal_url,
        updated_at=funding_request.updated_at,
        labels=funding_request.labels.all(),
        status=funding_request.review.review_result,
        payment_status=payment_status_viewmodel(payment_status, funding_request.request_id),
        journal_publisher_name=journal_publisher,
        journal_publisher_url=journal_publisher_url,
    )


def monograph_viewmodel(
    funding_request: FundingRequestModel, payment_status: PublicationPaymentStatus
) -> FundingRequestListViewModel:
    assert funding_request.publication.monograph_publisher is not None
    assert funding_request.review is not None
    publisher = funding_request.publication.monograph_publisher
    assert publisher is not None

    publisher_name = publisher.name
    publisher_url = publisher.get_absolute_url()
    return FundingRequestListViewModel(
        type="Monograph",
        id=funding_request.id,
        url=funding_request.get_absolute_url(),
        authors=[author.name for author in funding_request.publication.relevant_authors.all()],
        publication_title=funding_request.publication.title,
        publishing_entity_type="Publisher",
        publishing_entity_name=publisher_name,
        publishing_entity_url=publisher_url,
        updated_at=funding_request.updated_at,
        labels=funding_request.labels.all(),
        status=funding_request.review.review_result,
        payment_status=payment_status_viewmodel(payment_status, funding_request.request_id),
    )


def is_monograph(funding_request: FundingRequestModel) -> bool:
    return funding_request.publication.monograph_publisher is not None


def is_article(funding_request: FundingRequestModel) -> bool:
    return funding_request.publication.article_journal is not None


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


class PaymentStatusLookup:
    def __init__(self, payment_statuses: dict[int, PublicationPaymentStatus]) -> None:
        self._payment_statuses = payment_statuses

    def __call__(self, publication_id: int) -> PublicationPaymentStatus:
        return self._payment_statuses[publication_id]
