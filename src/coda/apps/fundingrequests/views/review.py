from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.contexts.fundingrequest.dto.commands import UpdateReviewDto
from coda.contexts.fundingrequest.services import checks, fundingrequests
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.money import Currency
from coda.apps.breadcrumbs.decorators import breadcrumb


@login_required
@breadcrumb("Review Funding Request", parent_url_name="fundingrequests:detail")
def review_page(request: HttpRequest, pk: int) -> HttpResponse:
    fr = repository.get_by_id(FundingRequestId(pk))
    return render(
        request,
        "fundingrequests/fundingrequest_review.html",
        {
            "fundingrequest": fr,
            "currencies": list(Currency),
            "selected_currency": fr.funding_amount.currency,
            "checks": checks.get_checkrun(FundingRequestId(pk)),
        },
    )


@login_required
@require_POST
def review_submit(request: HttpRequest, pk: int) -> HttpResponse:
    fid = FundingRequestId(pk)
    process_review(fid, request)
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": fid}))


def process_review(fid: FundingRequestId, request: HttpRequest) -> None:
    action = request.POST["action"]
    review_result = action if action != "return" else ""
    dto = UpdateReviewDto(
        decided_funding_amount=Decimal(request.POST["decided_funding_amount"]),
        decided_funding_currency=request.POST["decided_funding_currency"],
        reviewer_remarks=request.POST["reviewer_remarks"],
        result=review_result,
    )

    fundingrequests.update_review(fid, dto)
