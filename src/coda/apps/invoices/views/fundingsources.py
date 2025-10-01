from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.invoices.forms import FundingSourceForm
from coda.apps.invoices.models import FundingSource
from coda.apps.views import SimpleSearchEntityListView


class CreateFundingSourceView(LoginRequiredMixin, CreateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Source"}


fundingsource_createview = CreateFundingSourceView.as_view()


class UpdateFundingSourceView(LoginRequiredMixin, UpdateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    success_url = reverse_lazy("invoices:fundingsource_list")
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Update Funding Source"}


fundingsource_updateview = UpdateFundingSourceView.as_view()


class FundingSourceListView(LoginRequiredMixin, SimpleSearchEntityListView[FundingSource]):
    model = FundingSource
    entity_name = "Funding Sources"
    entity_create_url = "invoices:fundingsource_create"
    entity_list_item_template = "invoices/fundingsources/list.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True

fundingsource_listview = FundingSourceListView.as_view()


class FundingSourceDetailView(LoginRequiredMixin, DetailView[FundingSource]):
    model = FundingSource
    template_name = "invoices/fundingsources/detail.html"


fundingsource_detailview = FundingSourceDetailView.as_view()
