from typing import Any

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, UpdateView

from coda.apps.fundingrequests.forms import ExternalFundingFormset, FundingOrganizationLinkForm
from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
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
    queryset = FundingOrganization.objects.prefetch_related("links")


fundingorganizations_list = FundingOrganizationListView.as_view()


class FundingOrganizationForm(forms.ModelForm[FundingOrganization]):
    class Meta:
        model = FundingOrganization
        fields = ["name"]


class FundingOrganizationLinkFormMixin:
    request: HttpRequest

    def has_links(self) -> bool:
        return bool(self.request.POST.get("link_type") and self.request.POST.get("link_value"))

    def assemble_link_data(self) -> list[dict[str, Any]]:
        forms = self.link_forms()
        for form in forms:
            form.full_clean()
        return [{"link": form.get_form_data(), "errors": form.errors} for form in forms]

    def link_forms(self) -> list[FundingOrganizationLinkForm]:
        types = self.request.POST.getlist("link_type")
        values = self.request.POST.getlist("link_value")
        return [
            FundingOrganizationLinkForm({"link_type": t, "link_value": v})
            for t, v in zip(types, values)
        ]


@breadcrumb("Create Funding Organization", parent_url_name="fundingrequests:funders")
class FundingOrganizationCreateView(
    LoginRequiredMixin, FundingOrganizationLinkFormMixin, CreateView[FundingOrganization, FundingOrganizationForm]  # type: ignore[type-abstract]
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "fundingrequests/funders/funder_form.html"
    success_url = reverse_lazy("fundingrequests:funders")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Funding Organization"
        context["link_types"] = FundingOrganizationLinkType.objects.all()
        context["links"] = self.assemble_link_data() if self.has_links() else []
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        forms = self.link_forms()
        for f in forms:
            if not f.is_valid():
                return self.form_invalid(form)
        self.object = form.save()
        for f in forms:
            data = f.get_form_data()
            if data["link_type"] and data["link_value"]:
                link_type = FundingOrganizationLinkType.objects.get(name=data["link_type"])
                FundingOrganizationLink.objects.create(
                    funding_organization=self.object, type=link_type, value=data["link_value"]
                )
        from django.shortcuts import redirect as redirect_fn

        return redirect_fn(self.get_success_url())


fundingorganizations_create = FundingOrganizationCreateView.as_view()


@breadcrumb("Update Funding Organization", parent_url_name="fundingrequests:funders")
class FundingOrganizationUpdateView(
    LoginRequiredMixin, FundingOrganizationLinkFormMixin, UpdateView[FundingOrganization, FundingOrganizationForm]  # type: ignore[type-abstract]
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "fundingrequests/funders/funder_form.html"
    success_url = reverse_lazy("fundingrequests:funders")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Funding Organization"
        context["link_types"] = FundingOrganizationLinkType.objects.all()
        context["links"] = self._get_links_for_context()
        return context

    def _get_links_for_context(self) -> list[dict[str, Any]]:
        if self.has_links():
            return self.assemble_link_data()
        return [
            {"link": {"link_type": link.type.name, "link_value": link.value}, "errors": {}}
            for link in self.object.links.all()
        ]

    def form_valid(self, form: Any) -> HttpResponse:
        self.object = form.save()
        forms = self.link_forms()
        for link_form in forms:
            if not link_form.is_valid():
                return self.form_invalid(form)
        FundingOrganizationLink.objects.filter(funding_organization=self.object).delete()
        for link_form in forms:
            data = link_form.get_form_data()
            if data["link_type"] and data["link_value"]:
                link_type = FundingOrganizationLinkType.objects.get(name=data["link_type"])
                FundingOrganizationLink.objects.create(
                    funding_organization=self.object, type=link_type, value=data["link_value"]
                )
        from django.shortcuts import redirect as redirect_fn

        return redirect_fn(self.get_success_url())


fundingorganizations_update = FundingOrganizationUpdateView.as_view()


@login_required
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


@login_required
@require_POST
def add_funder_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "partials/linkrow.html",
        {"link_types": FundingOrganizationLinkType.objects.all()},
    )
