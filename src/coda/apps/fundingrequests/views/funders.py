from typing import Any

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.generic import CreateView, UpdateView

from coda.apps.fundingrequests.forms import ExternalFundingFormset
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.views import SimpleSearchEntityListView

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Funding Organizations", parent_url_name="fundingrequests:home")
class FundingOrganizationListView(
    LoginRequiredMixin, SimpleSearchEntityListView[FundingOrganization]
):
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


@breadcrumb("Create Funding Organization", parent_url_name="fundingrequests:funders")
class FundingOrganizationCreateView(
    LoginRequiredMixin, CreateView[FundingOrganization, FundingOrganizationForm]
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("fundingrequests:funders")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Funding Organization"}


fundingorganizations_create = FundingOrganizationCreateView.as_view()


@breadcrumb("Update Funding Organization", parent_url_name="fundingrequests:funders")
class FundingOrganizationUpdateView(
    LoginRequiredMixin, UpdateView[FundingOrganization, FundingOrganizationForm]
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("fundingrequests:funders")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Update Funding Organization"}


fundingorganizations_update = FundingOrganizationUpdateView.as_view()


@login_required
@require_http_methods(["DELETE", "POST"])
def fundingorganizations_delete(request: HttpRequest, pk: int) -> HttpResponse:
    fundingorganization = get_object_or_404(FundingOrganization, pk=pk)
    fundingorganization.delete()
    return HttpResponse()


@login_required
@require_GET
def fundingorganization_create_modal(request: HttpRequest) -> HttpResponse:
    form = FundingOrganizationForm()

    return render(
        request,
        "partials/entity_creation_modal.html",
        {
            "entity_name": "Funding Organization",
            "form": form,
            "entity_create_url": "fundingrequests:funders_create_modal_submit",
            "hx_include": "#wizard-form",
        },
    )


@login_required
@require_POST
def fundingorganization_create_modal_submit(request: HttpRequest) -> HttpResponse:
    form = FundingOrganizationForm(request.POST)

    if form.is_valid():
        organization = form.save()

        funding_formset = ExternalFundingFormset(request.POST)

        return render(
            request,
            "fundingrequests/funders/funder_create_success.html",
            {
                "organization": organization,
                "funding_formset": funding_formset,
            },
        )
    else:
        return render(
            request,
            "partials/entity_creation_modal.html",
            {
                "entity_name": "Funding Organization",
                "form": form,
                "entity_create_url": "fundingrequests:funders_create_modal_submit",
                "hx_include": "#wizard-form",
            },
        )
