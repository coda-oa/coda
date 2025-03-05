from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.fundingrequest import Review
from coda.fundingrequest import FundingRequestId
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
    review = repository.get_review(id)
    review = process_review(review, request)
    repository.save_review(review)
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": id}))


def process_review(review: Review, request: HttpRequest) -> Review:
    funding = Money(
        request.POST["decided_funding_amount"],
        Currency.from_code(request.POST["decided_funding_currency"]),
    )
    remarks = request.POST["reviewer_remarks"]

    action = request.POST["action"]
    match action:
        case "approve":
            review = review.approved(funding, remarks)
        case "reject":
            review = review.rejected(remarks)
        case "close":
            review = review.closed(remarks)
        case "waive":
            review = review.costs_waived(remarks)
        case "open":
            review = review.opened(remarks)
        case "return":
            review = review.with_remarks(remarks)

    return review
