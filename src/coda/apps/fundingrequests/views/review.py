from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services import checks
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.money import Currency, Money


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
            "checks": checks.get_checkrun(FundingRequestId(pk)),
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
            review = review.rejected(funding, remarks)
        case "close":
            review = review.closed(funding, remarks)
        case "waive":
            review = review.costs_waived(funding, remarks)
        case "open":
            review = review.opened(funding, remarks)
        case "return":
            review = review.with_remarks(decided_funding=funding, remarks=remarks)

    return review
