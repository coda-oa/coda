from typing import cast

from django.db.models.manager import BaseManager
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest
from coda.fundingrequest import Review


def view(request: HttpRequest) -> HttpResponse:
    open_requests = repository.search(processing_states=[Review.Open.value])
    rejected_requests = repository.search(processing_states=[Review.Rejected.value])
    approved_requests = repository.search(processing_states=[Review.Approved.value])
    return render(
        request,
        "pages/home.html",
        {
            "num_requests": FundingRequest.objects.count(),
            "num_open_requests": cast(BaseManager[FundingRequest], open_requests).count(),
            "num_rejected_requests": cast(BaseManager[FundingRequest], rejected_requests).count(),
            "num_approved_requests": cast(BaseManager[FundingRequest], approved_requests).count(),
        },
    )
