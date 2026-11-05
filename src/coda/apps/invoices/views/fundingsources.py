from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.institutions.models import Institution
from coda.apps.invoices import budget_query, invoice_query
from coda.apps.invoices.forms import FundingSourceForm
from coda.apps.invoices.models import FundingSource
from coda.apps.invoices.models import Invoice as InvoiceModel
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


def _balance_bar_widths(balance: budget_query.BudgetBalance) -> tuple[int, int]:
    """Spent/reserved percentages of the amount for the balance bar (spec
    §8.1.1); the bar caps at full width — no overfull segment."""
    amount = balance.amount.amount
    if amount <= 0:
        return 0, 0
    reserved = min(Decimal(100), balance.reserved.amount / amount * 100)
    spent = min(Decimal(100) - reserved, balance.spent.amount / amount * 100)
    return int(spent), int(reserved)


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


fundingsource_createview = CreateFundingSourceView.as_view()


@breadcrumb("Update Funding Source", parent_url_name="invoices:fundingsource_list")
class UpdateFundingSourceView(LoginRequiredMixin, UpdateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    form_class = FundingSourceForm
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "invoices/fundingsources/form.html"

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        self.object = self.get_object()
        if self.object.type == "institution":
            return _institution_redirect(self.object)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs) | {"title": "Update Funding Source"}
        if self.object and self.object.type == "budget":
            context["balance"] = budget_query.budget_balances(FundingSourceId(self.object.pk))
        return context


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
class FundingSourceDetailView(LoginRequiredMixin, DetailView[FundingSource]):
    model = FundingSource
    template_name = "invoices/fundingsources/detail.html"

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        self.object = self.get_object()
        if self.object.type == "institution":
            return _institution_redirect(self.object)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs) | {
            "transfer_targets": FundingSource.objects.exclude(pk=self.object.pk).filter(
                type="budget"
            ),
        }
        if self.object.type != "budget":
            return context

        context["balance"] = budget_query.budget_balances(FundingSourceId(self.object.pk))
        context["ledger"] = self.object.ledger_entries.order_by("-created_at")
        context["bar_spent_width"], context["bar_reserved_width"] = _balance_bar_widths(
            context["balance"]
        )
        # The invoices whose current funding assignments reference this
        # source (spec §8.1.2) — same Q the invoice list filters by.
        source_criterion = invoice_query.FundingSourceCriterion(
            FundingSourceId(self.object.pk)
        )
        context["recent_invoices"] = InvoiceModel.objects.filter(
            invoice_query.to_query(source_criterion)
        ).order_by("-date")[:10]
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
@require_POST
def budget_transfer(request: HttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(FundingSource, pk=pk)
    try:
        amount = Money(request.POST["amount"], Currency.from_code(source.budget_currency or "EUR"))
        budget_service.create_transfer(
            FundingSourceId(pk),
            FundingSourceId(int(request.POST["target"])),
            amount,
            request.POST.get("provenance_note", ""),
        )
    except (DomainError, KeyError, ValueError, InvalidOperation) as error:
        context = _detail_context(source) | {"transfer_error": str(error)}
        return render(request, "invoices/fundingsources/detail.html", context, status=200)

    return redirect("invoices:fundingsource_detail", pk=pk)


def _detail_context(source: FundingSource) -> dict[str, Any]:
    context: dict[str, Any] = {
        "fundingsource": source,
        "transfer_targets": FundingSource.objects.exclude(pk=source.pk).filter(type="budget"),
    }
    if source.type == "budget":
        context["balance"] = budget_query.budget_balances(FundingSourceId(source.pk))
        context["ledger"] = source.ledger_entries.order_by("-created_at")
        context["bar_spent_width"], context["bar_reserved_width"] = _balance_bar_widths(
            context["balance"]
        )
    return context
