from collections.abc import Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.fundingrequest import FundingRequest, FundingRequestId, Review


def fundingrequest_action(
    action: Callable[[FundingRequest], None],
) -> Callable[[HttpRequest], HttpResponse]:
    @login_required
    @require_POST
    def post(request: HttpRequest) -> HttpResponse:
        try:
            id = FundingRequestId(int(request.POST["fundingrequest"]))
            funding_request = repository.get_by_id(id)
            action(funding_request)
            FundingRequestModel.objects.filter(pk=id).update(
                processing_status=funding_request.review().value.lower()
            )
            return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request.id}))
        except FundingRequestModel.DoesNotExist:
            return HttpResponse(status=404)

    return post


approve = fundingrequest_action(lambda fr: fr.add_review(Review.Approved))
reject = fundingrequest_action(lambda fr: fr.add_review(Review.Rejected))
open = fundingrequest_action(FundingRequest.open)
