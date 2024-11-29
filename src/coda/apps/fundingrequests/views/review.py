from collections.abc import Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.forms import ReviewForm
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import fundingrequest_perform_review
from coda.fundingrequest import FundingRequestId, ReviewResult


def fundingrequest_action(review: ReviewResult) -> Callable[[HttpRequest], HttpResponse]:
    @login_required
    @require_POST
    def post(request: HttpRequest) -> HttpResponse:
        try:
            id = FundingRequestId(int(request.POST["fundingrequest"]))
            fundingrequest_perform_review(id, review)
            return redirect(reverse("fundingrequests:detail", kwargs={"pk": id}))
        except FundingRequestModel.DoesNotExist:
            return HttpResponse(status=404)

    return post


approve = fundingrequest_action(ReviewResult.Approved)
reject = fundingrequest_action(ReviewResult.Rejected)
open = fundingrequest_action(ReviewResult.Open)


def review_page(request: HttpRequest, pk: int) -> HttpResponse:
    fr = repository.get_by_id(FundingRequestId(pk))
    return render(
        request,
        "fundingrequests/fundingrequest_review.html",
        {"fundingrequest": fr, "form": ReviewForm()},
    )
