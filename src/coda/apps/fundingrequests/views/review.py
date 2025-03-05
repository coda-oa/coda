from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.fundingrequest.fundingrequest import AnyFundingRequest, FundingRequestId
from coda.money import Currency, Money


@login_required
def review_page(request: HttpRequest, pk: int) -> HttpResponse:
    fr = repository.get_by_id(FundingRequestId(pk))
    return render(
        request,
        "fundingrequests/fundingrequest_review.html",
        {
            "fundingrequest": fr,
            "currencies": list(Currency),
            "selected_currency": fr.funding_amount.currency,
        },
    )


@login_required
@require_POST
def review_submit(request: HttpRequest, pk: int) -> HttpResponse:
    id = FundingRequestId(pk)
    fr = repository.get_by_id(id)
    process_review(fr, request)
    repository.save_review(fr)
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": id}))


def process_review(fr: AnyFundingRequest, request: HttpRequest) -> None:
    funding = Money(
        request.POST["decided_funding_amount"],
        Currency.from_code(request.POST["decided_funding_currency"]),
    )
    remarks = request.POST["reviewer_remarks"]

    action = request.POST["action"]
    match action:
        case "approve":
            fr.approve(funding, remarks)
        case "reject":
            fr.reject(remarks)
        case "close":
            fr.close(remarks)
        case "waive":
            fr.waive_costs(remarks)
        case "open":
            fr.open(remarks)
        case "return":
            fr.update_remarks(remarks)
