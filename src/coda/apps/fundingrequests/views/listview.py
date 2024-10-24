import datetime
from collections.abc import Iterable
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.author import Author
from coda.date import DateRange

TEMPLATE_NAME = "fundingrequests/fundingrequest_list.html"


@login_required
def fundingrequest_list(request: HttpRequest) -> HttpResponse:
    paginator = Paginator(query(request), per_page=10)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, TEMPLATE_NAME, get_context_data(page))


def get_context_data(page: Page[FundingRequestModel]) -> dict[str, Any]:
    return {
        "labels": Label.objects.all(),
        "processing_states": FundingRequestModel.PROCESSING_CHOICES,
        "funding_requests": list(map(as_viewmodel, page.object_list)),
        "page_obj": page,
    }


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
