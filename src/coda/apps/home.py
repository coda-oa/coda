from typing import cast

from django.db.models.manager import BaseManager
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest, ProcessingStatus


def view(request: HttpRequest) -> HttpResponse:
    open_requests = repository.search(processing_states=[ProcessingStatus.IN_PROGRESS.value])
    rejected_requests = repository.search(processing_states=[ProcessingStatus.REJECTED.value])
    approved_requests = repository.search(processing_states=[ProcessingStatus.APPROVED.value])
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
