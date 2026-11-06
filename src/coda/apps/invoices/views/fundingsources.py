from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, UpdateView
from django_htmx.http import HttpResponseClientRedirect

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.institutions.models import Institution
from coda.apps.invoices import budget_query, invoice_query
from coda.apps.invoices.forms import FundingSourceForm
from coda.apps.invoices.models import FundingSource
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.search import words_icontains
from coda.apps.views import SimpleSearchEntityListView
from coda.contexts.finance.services import budget_service
from coda.domain.errors import DomainError
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.money import Currency, Money


@dataclass(frozen=True)
class BudgetStatus:
    label: str
    css_class: str


def _balance_bar_widths(
    balance: budget_query.BudgetBalance, allowance: Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Closed-form segment widths for the balance bar: returns (spent,
    reserved, available, over) as percentages. The available segment is
    always present — zero bookings renders a full available bar; the
    committed block (spent + reserved) is capped at amount + allowance and
    the hatched over-segment takes the remainder beyond the cap. Widths are
    normalized against ``max(amount + allowance, spent + reserved)`` and sum
    to ≤ 100 % of the pill."""
    amount = balance.amount.amount
    committed = balance.spent.amount + balance.reserved.amount
    cap = amount + allowance
    denominator = max(cap, committed)
    if denominator <= 0:
        # Zero-amount budget: the bar is all available (deliberate — the bar
        # must never be invisible).
        return Decimal(0), Decimal(0), Decimal(100), Decimal(0)
    available = max(Decimal(0), amount - committed) / denominator * 100
    block = min(committed, cap) / denominator * 100
    spent_share = (balance.spent.amount / committed) if committed else Decimal(0)
    reserved_share = (balance.reserved.amount / committed) if committed else Decimal(0)
    over = max(Decimal(0), committed - cap) / denominator * 100
    return (
        round(block * spent_share, 2),
        round(block * reserved_share, 2),
        round(available, 2),
        round(over, 2),
    )


@dataclass(frozen=True)
class BudgetListItem:
    id: int
    name: str
    balance: budget_query.BudgetBalance

    @property
    def status(self) -> BudgetStatus:
        if self.balance.available < Money(0, self.balance.available.currency):
            return BudgetStatus("exceeded", "danger")
        if self.balance.pending:
            return BudgetStatus("pending conversion", "warning")
        return BudgetStatus("within budget", "success")


@breadcrumb("Create Funding Source", parent_url_name="invoices:fundingsource_list")
class CreateFundingSourceView(LoginRequiredMixin, CreateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    form_class = FundingSourceForm
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "invoices/fundingsources/form.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Source"}

    def get_form_kwargs(self) -> dict[str, Any]:
        return super().get_form_kwargs() | {"home_currency": GlobalPreferences.get_home_currency}


fundingsource_createview = CreateFundingSourceView.as_view()


class InstitutionSourceRedirectMixin:
    """Fetches the funding source once per request and routes institution-type
    sources to their institution page — they have no funding-source page of
    their own. Place after ``LoginRequiredMixin`` so the auth check runs first;
    the cached ``get_object`` keeps ``dispatch`` from fetching the object a
    second time."""

    object: FundingSource

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        self.object = self.get_object()
        if self.object.type == "institution":
            return _institution_redirect(self.object)
        return cast(
            HttpResponseBase,
            super().dispatch(request, *args, **kwargs),  # type: ignore[misc]
        )

    def get_object(self, queryset: QuerySet[FundingSource] | None = None) -> FundingSource:
        if getattr(self, "object", None) is not None:
            return self.object
        return cast(FundingSource, super().get_object(queryset))  # type: ignore[misc]


@breadcrumb("Update Funding Source", parent_url_name="invoices:fundingsource_list")
class UpdateFundingSourceView(
    LoginRequiredMixin, InstitutionSourceRedirectMixin, UpdateView[FundingSource, FundingSourceForm]
):
    model = FundingSource
    form_class = FundingSourceForm
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "invoices/fundingsources/form.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs) | {"title": "Update Funding Source"}
        if self.object and self.object.type == "budget":
            context["balance"] = budget_query.budget_balances(FundingSourceId(self.object.pk))
        return context

    def get_form_kwargs(self) -> dict[str, Any]:
        return super().get_form_kwargs() | {"home_currency": GlobalPreferences.get_home_currency}


fundingsource_updateview = UpdateFundingSourceView.as_view()


@breadcrumb("Funding Sources", parent_url_name="invoices:finances_home")
class FundingSourceListView(LoginRequiredMixin, SimpleSearchEntityListView[FundingSource]):
    model = FundingSource
    entity_name = "Funding Sources"
    entity_create_url = "invoices:fundingsource_create"
    entity_list_item_template = "invoices/fundingsources/list.html"
    use_generic_entity_filter = True

    def get_entities(self, request: HttpRequest) -> Sequence[BudgetListItem]:  # type: ignore[override]
        search_term = request.GET.get("query", "").strip()
        fs = FundingSource.objects.filter(type="budget")
        if search_term:
            fs = fs.filter(words_icontains(search_term, "name"))

        return DomainQuerySet(  # type: ignore[type-var]
            fs.order_by("name"),
            lambda row: BudgetListItem(
                id=row.pk,
                name=row.name,
                balance=budget_query.budget_balances(FundingSourceId(row.pk)),
            ),
        )


fundingsource_listview = FundingSourceListView.as_view()


@breadcrumb("Funding Source Detail", parent_url_name="invoices:fundingsource_list")
class FundingSourceDetailView(
    LoginRequiredMixin, InstitutionSourceRedirectMixin, DetailView[FundingSource]
):
    model = FundingSource
    template_name = "invoices/fundingsources/detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs) | _detail_context(self.object)
        if self.object.type != "budget":
            return context

        # The invoices whose current funding assignments reference this
        # source — same Q the invoice list filters by. distinct(): an
        # invoice with several positions on the same budget joins once per
        # assignment and must be listed once.
        source_criterion = invoice_query.FundingSourceCriterion(FundingSourceId(self.object.pk))
        context["recent_invoices"] = (
            InvoiceModel.objects.filter(invoice_query.to_query(source_criterion))
            .distinct()
            .order_by("-date")[:10]
        )
        return context


fundingsource_detailview = FundingSourceDetailView.as_view()


def _institution_redirect(source: FundingSource) -> HttpResponse:
    """Institution-type funding sources are implicit byproducts with no
    funding-source page of their own; they route to their institution."""
    if source.institution_id is None:
        return redirect("institutions:list")
    institution = Institution.all_objects.get(pk=source.institution_id)
    return redirect("institutions:detail", pk=institution.pk)


@login_required
@require_GET
def budget_transfer_dialog(request: HttpRequest, pk: int) -> HttpResponse:
    """Renders the transfer dialog fragment: an htmx `<dialog open>` partial
    carrying both the transfer and the add-funds mode."""
    source = get_object_or_404(FundingSource, pk=pk)
    mode = request.GET.get("mode", "transfer")
    if mode not in {"transfer", "add_funds"}:
        mode = "transfer"
    context = _transfer_dialog_context(source, mode=mode)
    return render(request, "invoices/fundingsources/transfer_modal.html", context)


def _transfer_dialog_context(
    source: FundingSource, *, mode: str = "transfer", error: str | None = None
) -> dict[str, Any]:
    return {
        "fundingsource": source,
        "mode": mode,
        "transfer_targets": _transfer_targets(source),
        "transfer_url": reverse("invoices:budget_transfer", kwargs={"pk": source.pk}),
        "transfer_error": error,
    }


def _transfer_targets(source: FundingSource) -> QuerySet[FundingSource]:
    # Transfers book the amount on both endpoints; cross-currency pairs are
    # rejected by the service (create_transfer), so the dialog only offers
    # targets whose currency matches the source's.
    targets = FundingSource.objects.exclude(pk=source.pk).filter(type="budget")
    if source.budget_currency:
        targets = targets.filter(budget_currency=source.budget_currency)
    return targets


@login_required
@require_POST
def budget_transfer(request: HttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(FundingSource, pk=pk)
    mode = request.POST.get("mode", "transfer")
    try:
        raw_amount = request.POST.get("amount")
        if not raw_amount:
            raise ValueError("an amount is required")
        amount = Money(raw_amount, Currency.from_code(source.budget_currency or "EUR"))
        provenance = request.POST.get("provenance_note", "")
        if mode == "add_funds":
            budget_service.add_funds(FundingSourceId(pk), amount, provenance)
        else:
            target = request.POST.get("target") or ""
            try:
                target_id = FundingSourceId(int(target))
            except ValueError:
                raise ValueError("no target budget selected") from None
            budget_service.create_transfer(
                FundingSourceId(pk),
                target_id,
                amount,
                provenance,
            )
    except (DomainError, KeyError, ValueError, InvalidOperation) as error:
        context = _transfer_dialog_context(source, mode=mode, error=str(error))
        return render(
            request,
            "invoices/fundingsources/transfer_modal.html",
            context,
            status=200,
        )

    # htmx submits get a client redirect (full page reload with updated
    # balances); non-JS submits keep the plain 302 redirect.
    detail_url = reverse("invoices:fundingsource_detail", kwargs={"pk": pk})
    if request.htmx:  # type: ignore[attr-defined]
        return HttpResponseClientRedirect(detail_url)
    return redirect(detail_url)


def _detail_context(source: FundingSource) -> dict[str, Any]:
    context: dict[str, Any] = {
        "fundingsource": source,
        "transfer_targets": _transfer_targets(source),
        "home_currency": GlobalPreferences.get_home_currency().code,
    }
    if source.type == "budget":
        context["balance"] = budget_query.budget_balances(FundingSourceId(source.pk))
        context["ledger"] = source.ledger_entries.order_by("-created_at")
        allowance = Decimal(source.allowance_amount or 0)
        (
            bar_spent,
            bar_reserved,
            bar_available,
            bar_over,
        ) = _balance_bar_widths(context["balance"], allowance)
        context["bar_spent_width"] = bar_spent
        context["bar_reserved_width"] = bar_reserved
        context["bar_available_width"] = bar_available
        context["bar_over_width"] = bar_over
        # Gap compensation: rendered widths are calc(p% − k px) so the
        # inter-segment gaps never eat the pill's padding — each segment
        # carries its share of (n − 1) · 3px.
        nonzero = len([w for w in (bar_spent, bar_reserved, bar_available, bar_over) if w])
        context["bar_gap_comp_px"] = round((nonzero - 1) * 3 / nonzero, 2) if nonzero else 0
    return context
