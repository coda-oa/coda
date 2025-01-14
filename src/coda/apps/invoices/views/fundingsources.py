from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from coda.apps.invoices.forms import FundingSourceForm
from coda.apps.invoices.models import FundingSource


class CreateFundingSourceView(LoginRequiredMixin, CreateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    success_url = reverse_lazy("invoices:fundingsources")
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Source"}


fundingsource_createview = CreateFundingSourceView.as_view()


class UpdateFundingSourceView(LoginRequiredMixin, UpdateView[FundingSource, FundingSourceForm]):
    model = FundingSource
    success_url = reverse_lazy("invoices:fundingsources")
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Update Funding Source"}


fundingsource_updateview = UpdateFundingSourceView.as_view()


class FundingSourceListView(LoginRequiredMixin, ListView[FundingSource]):
    model = FundingSource
    template_name = "invoices/fundingsources/list.html"
    context_object_name = "fundingsources"


fundingsource_listview = FundingSourceListView.as_view()


class FundingSourceDetailView(LoginRequiredMixin, DetailView[FundingSource]):
    model = FundingSource
    template_name = "invoices/fundingsources/detail.html"


fundingsource_detailview = FundingSourceDetailView.as_view()
