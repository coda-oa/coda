import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, QueryDict
from django.urls import reverse
from django.views.generic.edit import FormView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.forms import ReviewForm, ReviewSplitForm, ReviewSplitFormSet
from coda.apps.invoices import budget_query
from coda.apps.invoices.models import FundingSource
from coda.contexts.finance.services import budget_service
from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto
from coda.contexts.fundingrequest.services import checks, fundingrequests
from coda.domain.errors import DomainError
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest import AnyFundingRequest, FundingRequestId
from coda.domain.money import Money


def _decimal_or_zero(value: str | None) -> Decimal:
    if not value:
        return Decimal(0)
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal(0)


def _int_value(value: str | list[object], default: int = 0) -> int:
    if not isinstance(value, str):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _without_split_row(data: QueryDict, index: str) -> QueryDict:
    """Rewrite the formset data without row ``index``, shifting later rows up."""
    try:
        removed = int(index)
    except ValueError:
        return data
    if removed < 0 or removed >= _int_value(data.get("funding_splits-TOTAL_FORMS", "0")):
        return data

    data = data.copy()
    shifted: dict[str, str] = {}
    for key in list(data.keys()):
        match = re.fullmatch(r"funding_splits-(\d+)-(.+)", key)
        if not match:
            continue
        row, field = int(match.group(1)), match.group(2)
        if row == removed:
            del data[key]
        elif row > removed:
            shifted[f"funding_splits-{row - 1}-{field}"] = data.pop(key)[0]
    data.update(shifted)
    data["funding_splits-TOTAL_FORMS"] = str(_int_value(data["funding_splits-TOTAL_FORMS"]) - 1)
    return data


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

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        """Add/remove markers re-render the full page before any action runs."""
        if "form_action_add" in request.POST:
            data = request.POST.copy()
            total = _int_value(data.get("funding_splits-TOTAL_FORMS", "0"))
            data["funding_splits-TOTAL_FORMS"] = str(total + 1)
            return self._rerender(data)
        if "form_action_remove" in request.POST:
            return self._rerender(_without_split_row(request.POST, request.POST["form_action_remove"]))
        return super().post(request, *args, **kwargs)

    def _rerender(self, data: QueryDict) -> HttpResponse:
        """Re-render the full page from (modified) POST data without saving.

        The review form's ``action`` field is display-only here; filling it
        keeps the required-field error off the re-rendered page."""
        if "action" not in data:
            data = data.copy()
            data["action"] = ReviewForm.ACTION_RETURN
        form = ReviewForm(data)
        return self.render_to_response(self.get_context_data(form=form, split_data=data))

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
        split_data = kwargs.pop("split_data", None)
        context = super().get_context_data(**kwargs) | {
            "fundingrequest": self._fundingrequest(),
            "checks": checks.get_checkrun(self._fid()),
        }
        if split_data is None and self.request.method == "POST":
            split_data = self.request.POST
        context |= self._split_section(context["fundingrequest"], split_data)
        context["budgets"] = self._budgets()
        return context

    def _budgets(self) -> list[dict[str, Any]]:
        return [
            {
                "id": str(budget.pk),
                "name": budget.name,
                "available": budget_query.budget_balances(FundingSourceId(budget.pk)).available,
            }
            for budget in FundingSource.objects.filter(type="budget")
        ]

    def _split_section(self, fundingrequest: AnyFundingRequest, split_data: QueryDict | None) -> dict[str, Any]:
        if split_data is not None:
            formset = ReviewSplitFormSet(split_data, prefix="funding_splits")
        else:
            formset = ReviewSplitFormSet(prefix="funding_splits")
            split_data = QueryDict("")

        budgets = {budget["id"]: budget for budget in self._budgets()}
        committed: dict[str, Decimal] = defaultdict(Decimal)
        entries: list[tuple[int, ReviewSplitForm, str, Decimal]] = []
        for index, split_form in enumerate(formset):
            source = split_data.get(f"funding_splits-{index}-funding_source") or ""
            amount = _decimal_or_zero(split_data.get(f"funding_splits-{index}-amount"))
            entries.append((index, split_form, source, amount))
            committed[source] += amount

        rows = []
        total = Decimal(0)
        for index, split_form, source, amount in entries:
            total += amount
            budget = budgets.get(source)
            if budget is None:
                rows.append({"index": index, "form": split_form, "gross_left": "", "feedback": ""})
                continue
            available: Money = budget["available"]
            gross_left = available - Money(amount, available.currency)
            # Sibling-aggregated: all posted rows on this budget commit together,
            # so the capacity verdict sees their sum, not the single row.
            capacity = budget_service.capacity_verdict(
                FundingSourceId(int(source)), Money(committed[source], available.currency)
            )
            feedback = "fits" if capacity.allowed else f"exceeds: only {available} gross-of-tax available"
            rows.append(
                {"index": index, "form": split_form, "gross_left": gross_left, "feedback": feedback}
            )

        decided = fundingrequest.funding_amount
        if split_data.get("decided_funding_amount"):
            decided = Money(
                _decimal_or_zero(split_data.get("decided_funding_amount")),
                fundingrequest.funding_amount.currency,
            )
        if total == decided.amount:
            verdict = "matches the decided amount ✓"
        else:
            verdict = f"difference {(decided.amount - total).quantize(Decimal('0.01'))}"
        return {
            "funding_splits": formset,
            "split_rows": rows,
            "split_total": f"{total.quantize(Decimal('0.01'))} {decided.currency.code}",
            "sum_verdict": verdict,
        }

    def _fid(self) -> FundingRequestId:
        return FundingRequestId(self.kwargs["pk"])

    def _fundingrequest(self) -> AnyFundingRequest:
        return repository.get_by_id(self._fid())


review_view = ReviewView.as_view()
