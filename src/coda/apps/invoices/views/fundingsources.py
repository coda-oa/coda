from collections.abc import Sequence
from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices.forms import FundingSourceForm
from coda.apps.search import words_icontains
from coda.apps.invoices.models import FundingSource
from coda.apps.views import SimpleSearchEntityListView

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Create Funding Source", parent_url_name="invoices:fundingsource_list")
class CreateFundingSourceView(LoginRequiredMixin, CreateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "generic_form_view.html"
    fields = ["name", "budget_amount"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Source"}


fundingsource_createview = CreateFundingSourceView.as_view()


@breadcrumb("Update Funding Source", parent_url_name="invoices:fundingsource_list")
class UpdateFundingSourceView(LoginRequiredMixin, UpdateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "generic_form_view.html"
    fields = ["name", "budget_amount"]

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


@breadcrumb("Funding Source Detail", parent_url_name="invoices:fundingsource_list")
class FundingSourceDetailView(LoginRequiredMixin, DetailView[FundingSource]):
    model = FundingSource
    template_name = "invoices/fundingsources/detail.html"


fundingsource_detailview = FundingSourceDetailView.as_view()
