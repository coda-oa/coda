from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse
from django.views.generic.edit import FormView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.forms import ReviewForm
from coda.contexts.fundingrequest.services import checks, fundingrequests
from coda.domain.fundingrequest import AnyFundingRequest, FundingRequestId


@breadcrumb("Review Funding Request", parent_url_name="fundingrequests:detail")
class ReviewView(LoginRequiredMixin, FormView[ReviewForm]):
    template_name = "fundingrequests/fundingrequest_review.html"
    form_class = ReviewForm

    def get_initial(self) -> dict[str, Any]:
        fundingrequest = self._fundingrequest()
        return {
            "decided_funding_amount": fundingrequest.funding_amount.amount,
            "decided_funding_currency": fundingrequest.funding_amount.currency.code,
            "reviewer_remarks": fundingrequest.review_remarks,
        }

    def form_valid(self, form: ReviewForm) -> HttpResponse:
        fundingrequests.update_review(self._fid(), form.to_dto())
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "fundingrequest": self._fundingrequest(),
            "checks": checks.get_checkrun(self._fid()),
        }

    def _fid(self) -> FundingRequestId:
        return FundingRequestId(self.kwargs["pk"])

    def _fundingrequest(self) -> AnyFundingRequest:
        return repository.get_by_id(self._fid())


review_view = ReviewView.as_view()
