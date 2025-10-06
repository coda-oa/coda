from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services import checks
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
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

    if action == "return":
        review = review.update_review(decided_funding=funding, remarks=remarks)
        
    else:
        result = ReviewResult.of(action)
        review = review.update_review(result, funding, remarks)
        
    return review
    