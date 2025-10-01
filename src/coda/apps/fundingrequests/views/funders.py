from typing import Any

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.views import SimpleSearchEntityListView 

from django.utils.decorators import method_decorator
from coda.apps.breadcrumbs.decorators import breadcrumb


@method_decorator(breadcrumb("Funding Organizations", parent_url_name="fundingrequests:home"), name="dispatch")
class FundingOrganizationListView(LoginRequiredMixin, SimpleSearchEntityListView[FundingOrganization]):
    model = FundingOrganization
    entity_name = "Funding Organizations"
    entity_create_url = "fundingrequests:funders_create"
    entity_list_item_template = "fundingrequests/funders/funder_list_item.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True
    
fundingorganizations_list = FundingOrganizationListView.as_view()


class FundingOrganizationForm(forms.ModelForm[FundingOrganization]):
    class Meta:
        model = FundingOrganization
        fields = ["name"]


@method_decorator(breadcrumb("Create Funding Organization", parent_url_name="fundingrequests:funders"), name="dispatch")
class FundingOrganizationCreateView(LoginRequiredMixin, CreateView[FundingOrganization, FundingOrganizationForm]
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("fundingrequests:funders")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Organization"}


fundingorganizations_create = FundingOrganizationCreateView.as_view()


@method_decorator(breadcrumb("Update Funding Organization", parent_url_name="fundingrequests:funders"), name="dispatch")
class FundingOrganizationUpdateView(LoginRequiredMixin, UpdateView[FundingOrganization, FundingOrganizationForm]
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("fundingrequests:funders")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Update Funding Organization"}


fundingorganizations_update = FundingOrganizationUpdateView.as_view()


@login_required
def fundingorganizations_delete(request: HttpRequest, pk: int) -> HttpResponse:
    fundingorganization = get_object_or_404(FundingOrganization, pk=pk)
    fundingorganization.delete()
    return HttpResponse()
