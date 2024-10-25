import datetime
from collections.abc import Iterable
from typing import Any, NamedTuple, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.views import EntityListView
from coda.author import Author
from coda.date import DateRange


class FundingRequestListView(EntityListView["ListViewModel"], LoginRequiredMixin):
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"
    entity_filter_template = "fundingrequests/forms/fundingrequest_filter.html"

    def get_entities(self, request: HttpRequest) -> list["ListViewModel"]:
        return [as_viewmodel(fr) for fr in query(request)]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        return ctx | {
            "labels": Label.objects.all(),
            "processing_states": FundingRequestModel.PROCESSING_CHOICES,
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
            processing_states=request.GET.getlist("processing_status"),
        ),
    )


class ListViewModel(NamedTuple):
    id: int
    url: str
    publication_title: str
    submitter_name: str
    journal_title: str
    journal_url: str
    updated_at: datetime.date
    labels: Iterable[Label]
    status: str


def as_viewmodel(funding_request: FundingRequestModel) -> ListViewModel:
    return ListViewModel(
        id=funding_request.id,
        url=funding_request.get_absolute_url(),
        publication_title=funding_request.publication.title,
        submitter_name=cast(Author, funding_request.submitter).name,
        journal_title=funding_request.publication.journal.title,
        journal_url=funding_request.publication.journal.get_absolute_url(),
        updated_at=funding_request.updated_at,
        labels=funding_request.labels.all(),
        status=funding_request.processing_status,
    )
