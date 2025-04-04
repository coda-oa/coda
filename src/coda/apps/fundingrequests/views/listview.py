import datetime
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal, NamedTuple, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.views.detailview import payment_status_viewmodel
from coda.apps.publications.services import publications
from coda.apps.views import EntityListView
from coda.domain.date import DateRange
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.payment import (
    InvoiceReceived,
    PublicationCoveredByContract,
    PublicationPaid,
    PublicationPaymentStatus,
    PublicationUnpaid,
)
from coda.domain.publication.publication import PublicationId

_advanced_search_fields = [
    "labels",
    "exclude_labels",
    "processing_status",
    "open_access_type",
    "payment_status",
    "start_date",
    "end_date",
]

_payment_status_map = {
    "paid": PublicationPaid,
    "unpaid": PublicationUnpaid,
    "invoice_received": InvoiceReceived,
    "covered_by_contract": PublicationCoveredByContract,
}

_payment_status_choices = [
    ("paid", "Paid"),
    ("unpaid", "Unpaid"),
    ("invoice_received", "Invoice Received"),
    ("covered_by_contract", "Covered by Contract"),
]


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

        expand_advanced_search = any(self.request.GET.get(key) for key in _advanced_search_fields)

        labels = Label.objects.all()
        return ctx | {
            "labels": labels,
            "exlude_labels": labels,
            "processing_states": [rr.value for rr in ReviewResult],
            "open_access_types": [oat.value for oat in OpenAccessType],
            "expand_advanced_search": expand_advanced_search,
            "payment_status_choices": _payment_status_choices,
        }


fundingrequest_list = FundingRequestListView.as_view()


def query(request: HttpRequest) -> QuerySet[FundingRequestModel]:
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    date_range = DateRange.try_fromisoformat(start=start_date, end=end_date)
    requested_payment_statuses = [
        _payment_status_map[status] for status in request.GET.getlist("payment_status")
    ]

    return cast(
        QuerySet[FundingRequestModel],
        repository.search(
            generic_search=request.GET.get("search_term"),
            date_range=date_range,
            labels=list(map(int, request.GET.getlist("labels"))),
            exclude_labels=list(map(int, request.GET.getlist("exclude_labels"))),
            processing_states=[ReviewResult(rr) for rr in request.GET.getlist("processing_status")],
            open_access_types=[
                OpenAccessType(oat) for oat in request.GET.getlist("open_access_type")
            ],
            payment_statuses=requested_payment_statuses,
        ),
    )


class FundingRequestListViewModel(NamedTuple):
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
        payment_status=payment_status_viewmodel(payment_status),
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
        payment_status=payment_status_viewmodel(payment_status),
    )


def is_monograph(funding_request: FundingRequestModel) -> bool:
    return funding_request.publication.monograph_publisher is not None


def is_article(funding_request: FundingRequestModel) -> bool:
    return funding_request.publication.article_journal is not None


class PaymentStatusLookup:
    def __init__(self, payment_statuses: dict[int, PublicationPaymentStatus]) -> None:
        self._payment_statuses = payment_statuses

    def __call__(self, publication_id: int) -> PublicationPaymentStatus:
        return self._payment_statuses[publication_id]
