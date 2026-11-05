import re
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


def _decimal_or_none(value: str | None) -> Decimal | None:
    """Parses a posted amount; ``None`` marks it invalid so the row feedback
    can surface it instead of silently zeroing the live sum."""
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _source_id(source: str) -> FundingSourceId | None:
    try:
        return FundingSourceId(int(source))
    except ValueError:
        return None


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
        budgets = self._budgets()
        context["budgets"] = budgets
        context |= self._split_section(context["fundingrequest"], split_data, budgets)
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

    def _split_section(
        self,
        fundingrequest: AnyFundingRequest,
        split_data: QueryDict | None,
        budgets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if split_data is not None:
            formset = ReviewSplitFormSet(split_data, prefix="funding_splits")
        else:
            formset = ReviewSplitFormSet(prefix="funding_splits")
            split_data = QueryDict("")

        decided = fundingrequest.funding_amount
        parsed_decided = _decimal_or_none(split_data.get("decided_funding_amount"))
        if split_data.get("decided_funding_amount") and parsed_decided is not None:
            decided = Money(parsed_decided, fundingrequest.funding_amount.currency)

        entries: list[tuple[int, ReviewSplitForm, str, Decimal, bool]] = []
        commitments: list[tuple[FundingSourceId, Money]] = []
        for index, split_form in enumerate(formset):
            source = split_data.get(f"funding_splits-{index}-funding_source") or ""
            raw_amount = split_data.get(f"funding_splits-{index}-amount")
            amount = _decimal_or_none(raw_amount)
            invalid = amount is None and bool(raw_amount)
            entries.append((index, split_form, source, amount or Decimal(0), invalid))
            source_id = _source_id(source)
            if source_id is not None:
                # The preview checks capacity on the sum of all rows per
                # budget, in the decided-funding currency — exactly the basis
                # save-time ensure_capacity uses. The cross-currency
                # comparison TypeError for foreign-currency budgets is
                # pre-existing at save time and out of scope here.
                commitments.append((source_id, Money(amount or Decimal(0), decided.currency)))

        committed = budget_service.committed_per_funding_source(commitments)
        verdicts = {
            source_id: budget_service.capacity_verdict(source_id, amount)
            for source_id, amount in committed.items()
            if str(source_id) in {budget["id"] for budget in budgets}
        }

        rows = []
        total = Decimal(0)
        for index, split_form, source, amount, invalid in entries:
            total += amount
            source_id = _source_id(source)
            capacity = verdicts.get(source_id) if source_id is not None else None
            if capacity is None:
                rows.append(
                    {
                        "index": index,
                        "form": split_form,
                        "gross_left": "",
                        "feedback": "invalid amount" if invalid else "",
                        "amount_invalid": invalid,
                    }
                )
                continue
            if invalid:
                feedback, amount_invalid = "invalid amount", True
            else:
                amount_invalid = False
                feedback = (
                    "fits"
                    if capacity.allowed
                    else f"exceeds: only {capacity.available_after} "
                    "gross-of-tax available, over-budget not allowed"
                )
            rows.append(
                {
                    "index": index,
                    "form": split_form,
                    # Aggregated across all rows on this budget (spec §8.3.1):
                    # the verdict is computed on the sibling sum, so the
                    # gross-left figure is what remains after all of them.
                    "gross_left": capacity.available_after,
                    "feedback": feedback,
                    "amount_invalid": amount_invalid,
                }
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
