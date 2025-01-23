import datetime
from collections.abc import Iterable
from typing import Any, Literal, NamedTuple, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.views import EntityListView
from coda.author import Author
from coda.date import DateRange
from coda.fundingrequest import ReviewResult
from coda.publication import OpenAccessType


class FundingRequestListView(LoginRequiredMixin, EntityListView["FundingRequestListViewModel"]):
    template_name = "fundingrequests/fundingrequest_list.html"
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"
    entity_filter_template = "fundingrequests/forms/fundingrequest_filter.html"

    _advanced_search_fields = [
        "labels",
        "processing_status",
        "open_access_type",
        "start_date",
        "end_date",
    ]

    def get_entities(self, request: HttpRequest) -> list["FundingRequestListViewModel"]:
        return [as_viewmodel(fr) for fr in query(request)]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)

        expand_advanced_search = any(
            self.request.GET.get(key) for key in self._advanced_search_fields
        )

        return ctx | {
            "labels": Label.objects.all(),
            "processing_states": [rr.value for rr in ReviewResult],
            "open_access_types": [oat.value for oat in OpenAccessType],
            "expand_advanced_search": expand_advanced_search,
        }


fundingrequest_list = FundingRequestListView.as_view()


def query(request: HttpRequest) -> QuerySet[FundingRequestModel]:
    search_type = request.GET.get("search_type")
    if search_type in ["title", "submitter", "publisher"]:
        search_args = {search_type: request.GET.get("search_term")}
    else:
        search_args = {}

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    date_range = DateRange.try_fromisoformat(start=start_date, end=end_date)

    return cast(
        QuerySet[FundingRequestModel],
        repository.search(
            **search_args,
            date_range=date_range,
            labels=list(map(int, request.GET.getlist("labels"))),
            processing_states=[ReviewResult(rr) for rr in request.GET.getlist("processing_status")],
            open_access_types=[
                OpenAccessType(oat) for oat in request.GET.getlist("open_access_type")
            ],
        ),
    )


class FundingRequestListViewModel(NamedTuple):
    type: Literal["Article", "Monograph"]
    id: int
    url: str
    publication_title: str
    submitter_name: str
    publishing_entity_type: Literal["Journal", "Publisher"]
    publishing_entity_name: str
    publishing_entity_url: str
    updated_at: datetime.date
    labels: Iterable[Label]
    status: str


def as_viewmodel(
    funding_request: FundingRequestModel,
) -> FundingRequestListViewModel:
    if is_article(funding_request):
        return article_viewmodel(funding_request)
    elif is_monograph(funding_request):
        return monograph_viewmodel(funding_request)

    raise ValueError("Funding request is neither an article nor a monograph.")


def article_viewmodel(funding_request: FundingRequestModel) -> FundingRequestListViewModel:
    journal = funding_request.publication.article_journal
    assert journal is not None

    journal_title = journal.title
    journal_url = journal.get_absolute_url()
    return FundingRequestListViewModel(
        type="Article",
        id=funding_request.id,
        url=funding_request.get_absolute_url(),
        publication_title=funding_request.publication.title,
        submitter_name=cast(Author, funding_request.submitter).name,
        publishing_entity_type="Journal",
        publishing_entity_name=journal_title,
        publishing_entity_url=journal_url,
        updated_at=funding_request.updated_at,
        labels=funding_request.labels.all(),
        status=funding_request.processing_status,
    )


def monograph_viewmodel(funding_request: FundingRequestModel) -> FundingRequestListViewModel:
    publisher = funding_request.publication.monograph_publisher
    assert publisher is not None

    publisher_name = publisher.name
    publisher_url = publisher.get_absolute_url()
    return FundingRequestListViewModel(
        type="Monograph",
        id=funding_request.id,
        url=funding_request.get_absolute_url(),
        publication_title=funding_request.publication.title,
        submitter_name=cast(Author, funding_request.submitter).name,
        publishing_entity_type="Publisher",
        publishing_entity_name=publisher_name,
        publishing_entity_url=publisher_url,
        updated_at=funding_request.updated_at,
        labels=funding_request.labels.all(),
        status=funding_request.processing_status,
    )


def is_monograph(funding_request: FundingRequestModel) -> bool:
    return funding_request.publication.monograph_publisher is not None


def is_article(funding_request: FundingRequestModel) -> bool:
    return funding_request.publication.article_journal is not None
