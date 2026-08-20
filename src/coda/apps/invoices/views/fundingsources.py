from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices.forms import FundingSourceForm
from coda.apps.invoices.funding_summary import funding_source_summary
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.search import words_icontains
from coda.apps.invoices.models import FundingSource
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.money import Money

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Create Funding Source", parent_url_name="invoices:fundingsource_list")
class CreateFundingSourceView(LoginRequiredMixin, CreateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    template_name = "generic_form_view.html"
    fields = ["name", "budget_amount"]

    def get_success_url(self) -> str:
        assert self.object is not None
        return reverse("invoices:fundingsource_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Source"}


fundingsource_createview = CreateFundingSourceView.as_view()


@breadcrumb("Update Funding Source", parent_url_name="invoices:fundingsource_detail")
class UpdateFundingSourceView(LoginRequiredMixin, UpdateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    template_name = "generic_form_view.html"
    fields = ["name", "budget_amount"]

    def get_success_url(self) -> str:
        assert self.object is not None
        return reverse("invoices:fundingsource_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Update Funding Source"}


fundingsource_updateview = UpdateFundingSourceView.as_view()


@breadcrumb("Funding Sources", parent_url_name="invoices:finances_home")
class FundingSourceListView(LoginRequiredMixin, SimpleSearchEntityListView[FundingSource]):
    model = FundingSource
    entity_name = "Funding Sources"
    entity_create_url = "invoices:fundingsource_create"
    entity_list_item_template = "invoices/fundingsources/list.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True

    def get_entities(self, request: HttpRequest) -> Sequence[FundingSource]:
        search_term = request.GET.get("query", "").strip()
        fs = FundingSource.objects.filter(type="budget")
        if search_term:
            fs = fs.filter(words_icontains(search_term, "name"))

        return DomainQuerySet(fs, lambda fs: fs)


fundingsource_listview = FundingSourceListView.as_view()


def _percentage(amount: Money, denominator: Decimal) -> float:
    if denominator <= 0:
        return 0.0
    return float(round(amount.amount / denominator * 100, 2))


@breadcrumb("Funding Source Detail", parent_url_name="invoices:fundingsource_list")
class FundingSourceDetailView(LoginRequiredMixin, DetailView[FundingSource]):
    model = FundingSource
    template_name = "invoices/fundingsources/detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        funding_source = self.object
        home_currency = GlobalPreferences.get_home_currency()
        summary = funding_source_summary(funding_source, home_currency)

        context["home_currency"] = home_currency
        context["spent"] = summary.spent
        context["reserved"] = summary.reserved
        context["invoices"] = summary.invoices
        context["unconverted_invoices"] = summary.unconverted

        if funding_source.type == FundingSource.TypeChoices.budget:
            context["is_budget"] = True
            if funding_source.budget_amount:
                total = Money(funding_source.budget_amount, home_currency)
                remaining = max(total - summary.spent - summary.reserved, Money(0, home_currency))
                denominator = max(total.amount, summary.spent.amount + summary.reserved.amount)
                context["budget_total"] = total
                context["remaining"] = remaining
                context["bar_total"] = total.amount
                context["bar_spent"] = summary.spent.amount
                context["bar_reserved"] = summary.reserved.amount
                context["bar_remaining"] = remaining.amount
                context["spent_pct"] = _percentage(summary.spent, denominator)
                context["reserved_pct"] = _percentage(summary.reserved, denominator)
                context["remaining_pct"] = _percentage(remaining, denominator)

        return context


fundingsource_detailview = FundingSourceDetailView.as_view()
