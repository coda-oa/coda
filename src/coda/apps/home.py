from typing import cast

from django.conf import settings
from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.models import FundingRequest
from coda.domain.fundingrequest.review import ReviewResult


def view(request: HttpRequest) -> HttpResponse:
    open_requests = fq.search(fq.ReviewResultCriteria([ReviewResult.Open]))
    rejected_requests = fq.search(fq.ReviewResultCriteria([ReviewResult.Rejected]))
    approved_requests = fq.search(fq.ReviewResultCriteria([ReviewResult.Approved]))

    if settings.CODA_DEMO_MODE:
        messages.warning(request, "CODA is running in demo mode.")
        messages.warning(request, "Data may be reset at any time.")

    return render(
        request,
        "pages/home.html",
        {
            "num_requests": FundingRequest.objects.count(),
            "num_open_requests": cast(QuerySet[FundingRequest], open_requests).count(),
            "num_rejected_requests": cast(QuerySet[FundingRequest], rejected_requests).count(),
            "num_approved_requests": cast(QuerySet[FundingRequest], approved_requests).count(),
        },
    )
