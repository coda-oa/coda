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
from coda.domain.fundingrequest.review import (
    DecidedFunding,
    FundingSplits,
    Review,
    ReviewSplit,
)
from coda.domain.money import Currency, Money


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
        """Add/remove/refresh markers re-render the full page before any
        action runs."""
        if "form_action_refresh" in request.POST:
            return self._rerender(request.POST)
        if "form_action_add" in request.POST:
            data = request.POST.copy()
            total = _int_value(data.get("funding_splits-TOTAL_FORMS", "0"))
            data["funding_splits-TOTAL_FORMS"] = str(total + 1)
            return self._rerender(data)
        if "form_action_remove" in request.POST:
            return self._rerender(
                _without_split_row(request.POST, request.POST["form_action_remove"])
            )
        return super().post(request, *args, **kwargs)

    def _rerender(self, data: QueryDict) -> HttpResponse:
        """Re-render the full page from (modified) POST data without saving.

        The review form's ``action`` field is display-only here; filling it
        keeps the required-field error off the re-rendered page. The form's
        other field errors are suppressed too: add/remove/refresh re-renders
        happen mid-edit, where "this field is required" noise is premature —
        real validation runs on the actual submit."""
        if "action" not in data:
            data = data.copy()
            data["action"] = ReviewForm.ACTION_RETURN
        form = ReviewForm(data)
        form.errors.clear()
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

    _review_cache: Review | None = None

    def _review(self) -> Review:
        """The request's review, round-tripped through the domain (its
        funding splits included). One query per render; the ``fundingrequest``
        object from ``get_by_id`` carries no splits."""
        if self._review_cache is None:
            self._review_cache = repository.get_review(self._fid())
        return self._review_cache

    def _own_split_totals(self) -> dict[int, Decimal]:
        """The review's own persisted split totals per funding source.

        Amounts pinned to the persisted decision's currency (the round-trip's
        pin); keyed by funding source id."""
        totals: dict[int, Decimal] = {}
        for split in self._review().funding_splits.splits:
            totals[split.funding_source] = (
                totals.get(split.funding_source, Decimal(0)) + split.amount.amount
            )
        return totals

    def _budgets(self) -> list[dict[str, Any]]:
        """The budgets for the review page's split section.

        Per-budget available excludes this review's own persisted splits, so
        the reviewer deciding a re-opened review sees the capacity they are
        actually deciding against. The budget detail page keeps its default
        semantics."""
        own = self._own_split_totals()
        # Own amounts are pinned to the persisted decision's currency; adding
        # them back into a budget's available is only meaningful when that
        # matches the budget's currency — a stale decision's amounts must not
        # be re-interpreted (the save rejects them too).
        persisted_currency = self._review().decided_funding.currency
        return [
            {
                "id": str(budget.pk),
                "name": budget.name,
                # Budget-type rows always carry a currency: the form and the
                # database require it. The fallback mirrors the balance
                # lookup below, so a legacy null can never render a
                # currencyless mismatch message.
                "currency": budget.budget_currency or "EUR",
                "available": budget_query.budget_balances(FundingSourceId(budget.pk)).available
                + Money(
                    own.get(budget.pk, Decimal(0))
                    if persisted_currency.code == (budget.budget_currency or "EUR")
                    else Decimal(0),
                    Currency[budget.budget_currency or "EUR"],
                ),
            }
            for budget in FundingSource.objects.filter(type="budget")
        ]

    def _split_section(
        self,
        fundingrequest: AnyFundingRequest,
        split_data: QueryDict | None,
        budgets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # The review's own persisted splits sit in the balance until
        # save_review replaces them — the prefill reads them and the
        # capacity verdicts exempt them: only the positive delta over own
        # totals is capacity-checked, mirroring the write path.
        persisted = [
            (split.funding_source, split.amount.amount)
            for split in self._review().funding_splits.splits
        ]
        own = self._own_split_totals()

        if split_data is not None:
            formset = ReviewSplitFormSet(split_data, prefix="funding_splits")
        else:
            # GET (re-open): prefill editable rows from the persisted splits,
            # feeding both the formset and the feedback/sum path (the
            # synthesized data below is what the feedback loop reads).
            initial = [
                {"funding_source": str(persisted_source_id), "amount": persisted_amount}
                for persisted_source_id, persisted_amount in persisted
            ]
            formset = ReviewSplitFormSet(initial=initial, prefix="funding_splits")
            split_data = QueryDict("", mutable=True)
            split_data["funding_splits-TOTAL_FORMS"] = str(len(initial) + 1)  # extra=1 blank
            split_data["funding_splits-INITIAL_FORMS"] = "0"
            for index, (persisted_source_id, persisted_amount) in enumerate(persisted):
                split_data[f"funding_splits-{index}-funding_source"] = str(persisted_source_id)
                split_data[f"funding_splits-{index}-amount"] = str(persisted_amount)

        decided = fundingrequest.funding_amount
        parsed_decided = _decimal_or_none(split_data.get("decided_funding_amount"))
        # The posted currency is authoritative — save validates splits against
        # it, so the preview must judge the same currency the reviewer chose,
        # not the persisted one. Unknown codes (crafted POSTs) keep the
        # persisted currency rather than crashing the render.
        posted_currency = split_data.get("decided_funding_currency")
        if posted_currency in Currency.allcodes():
            decided = Money(decided.amount, Currency.from_code(posted_currency))
        if split_data.get("decided_funding_amount") and parsed_decided is not None:
            decided = Money(parsed_decided, decided.currency)

        entries: list[tuple[int, ReviewSplitForm, str, Decimal, bool]] = []
        review_splits: list[ReviewSplit] = []
        for index, split_form in enumerate(formset):
            source = split_data.get(f"funding_splits-{index}-funding_source") or ""
            raw_amount = split_data.get(f"funding_splits-{index}-amount")
            amount = _decimal_or_none(raw_amount)
            invalid = amount is None and bool(raw_amount)
            entries.append((index, split_form, source, amount or Decimal(0), invalid))
            source_id = _source_id(source)
            if source_id is not None:
                # The preview checks capacity on the sum of all rows per
                # budget, in the decided-funding currency — the same basis
                # save-time ensure_capacity uses once _validate_splits has
                # pinned every split to its budget's currency.
                review_splits.append(
                    ReviewSplit(source_id, Money(amount or Decimal(0), decided.currency))
                )

        posted = DecidedFunding(decided, FundingSplits.of(review_splits))
        committed = posted.splits.totals()
        budget_currencies = {budget["id"]: budget["currency"] for budget in budgets}
        budget_names = {budget["id"]: budget["name"] for budget in budgets}
        # A stale decision's persisted splits are not exempted from the
        # capacity check: the save rejects them (the decided currency changed),
        # so the preview flags them instead of rendering a verdict. They are
        # also kept out of the persisted side of the delta — their amounts
        # belong to the old decision's currency and must not be re-interpreted.
        persisted_splits = self._review().funding_splits
        persisted_currency = self._review().decided_funding.currency
        stale_sources: set[FundingSourceId] = set()
        if persisted_currency != decided.currency:
            stale_sources = {sid for sid in committed if sid in persisted_splits.sources()}
            persisted_splits = FundingSplits.of(
                [
                    split
                    for split in persisted_splits.splits
                    if split.funding_source not in stale_sources
                ]
            )
        deltas = posted.delta_over(persisted_splits)
        verdicts = {}
        currency_mismatches: dict[FundingSourceId, str] = {}
        for source_id, committed_amount in committed.items():
            if str(source_id) not in budget_currencies:
                continue
            if source_id in stale_sources:
                currency_mismatches[source_id] = (
                    f"the persisted funding splits belong to the old decision "
                    f"({persisted_currency.code}) — re-enter the funding splits"
                )
                continue
            if budget_currencies[str(source_id)] != committed_amount.currency.code:
                # Splits are counted in the budget's currency; the save path
                # rejects a cross-currency split, so the preview renders that
                # reason instead of a cross-currency comparison that would
                # crash with TypeError.
                currency_mismatches[source_id] = (
                    f"funding split for budget '{budget_names[str(source_id)]}' is decided in "
                    f"{committed_amount.currency.code}, but the budget is denominated in "
                    f"{budget_currencies[str(source_id)]}"
                )
                continue
            verdicts[source_id] = budget_service.capacity_verdict(
                source_id,
                deltas.get(source_id, Money(0, committed_amount.currency)),
            )

        rows = []
        total = Decimal(0)
        for index, split_form, source, amount, invalid in entries:
            total += amount
            source_id = _source_id(source)
            capacity = verdicts.get(source_id) if source_id is not None else None
            mismatch = currency_mismatches.get(source_id) if source_id is not None else None
            if mismatch is not None:
                rows.append(
                    {
                        "index": index,
                        "form": split_form,
                        "gross_left": "",
                        "feedback": mismatch,
                        "amount_invalid": False,
                    }
                )
                continue
            if capacity is None or source_id is None:
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
                    # Aggregated across all rows on this budget: the verdict
                    # is computed on the delta over the review's own persisted
                    # splits, so the displayed figure adds them back. It
                    # agrees with the own-excluded per-budget available in
                    # the budgets context.
                    "gross_left": capacity.available_after
                    + Money(own.get(source_id, Decimal(0)), capacity.available_after.currency),
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
