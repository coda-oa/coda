from collections.abc import Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import fundingrequest_perform_review
from coda.fundingrequest import FundingRequestId, Review


def fundingrequest_action(review: Review) -> Callable[[HttpRequest], HttpResponse]:
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


approve = fundingrequest_action(Review.Approved)
reject = fundingrequest_action(Review.Rejected)
open = fundingrequest_action(Review.Open)
