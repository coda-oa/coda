from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse
from django.views.generic.edit import FormView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.forms import ReviewForm, ReviewSplitFormSet
from coda.apps.invoices import budget_query
from coda.apps.invoices.models import FundingSource
from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto
from coda.contexts.fundingrequest.services import checks, fundingrequests
from coda.domain.errors import DomainError
from coda.domain.finance.invoice import FundingSourceId
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
        splits: list[ReviewSplitDto] = []
        if "funding_splits-TOTAL_FORMS" in self.request.POST:
            formset = ReviewSplitFormSet(self.request.POST, prefix="funding_splits")
            if not formset.is_valid():
                form.add_error(None, "The funding attribution is invalid.")
                return self.form_invalid(form)

            splits = [
                split_form.to_dto()
                for split_form in formset
                if split_form.has_changed() and split_form.cleaned_data.get("funding_source")
            ]

        try:
            fundingrequests.update_review(self._fid(), form.to_dto(splits))
        except DomainError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs) | {
            "fundingrequest": self._fundingrequest(),
            "checks": checks.get_checkrun(self._fid()),
        }
        context["funding_splits"] = ReviewSplitFormSet(prefix="funding_splits")
        context["budgets"] = [
            {
                "name": budget.name,
                "available": budget_query.budget_balances(FundingSourceId(budget.pk)).available,
            }
            for budget in FundingSource.objects.filter(type="budget")
        ]
        return context

    def _fid(self) -> FundingRequestId:
        return FundingRequestId(self.kwargs["pk"])

    def _fundingrequest(self) -> AnyFundingRequest:
        return repository.get_by_id(self._fid())


review_view = ReviewView.as_view()
