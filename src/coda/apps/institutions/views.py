from io import BytesIO
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.institutions import services
from coda.apps.institutions.forms import InstitutionForm
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.views import SimpleSearchEntityListView


@breadcrumb("Organization Structure")
class InstitutionListView(LoginRequiredMixin, SimpleSearchEntityListView[Institution]):
    model = Institution
    template_name = "institutions/institution_list.html"
    entity_name = "Organization Structure"
    entity_list_item_template = "institutions/institution_list_item.html"
    entity_create_url = "institutions:create"
    entity_secondary_create_url = "institutions:import_view"
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"
    search_placeholder = "Search institutions..."

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "entity_secondary_create_url": self.entity_secondary_create_url
        }


institution_list_view = InstitutionListView.as_view()


@breadcrumb("Create Institution", parent_url_name="institutions:list")
class CreateInstitutionView(LoginRequiredMixin, CreateView[Institution, InstitutionForm]):
    template_name = "institutions/institution_form.html"
    model = Institution
    form_class = InstitutionForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Institution"
        context["link_types"] = InstitutionLinkType.objects.all()
        return context

    def form_valid(self, form: InstitutionForm) -> HttpResponse:
        self.object = form.save()

        link_types = self.request.POST.getlist("link_type")
        link_values = self.request.POST.getlist("link_value")

        for type_id, value in zip(link_types, link_values):
            if type_id and value:
                InstitutionLink.objects.create(
                    institution=self.object,
                    type_id=type_id,
                    value=value,
                )

        messages.success(self.request, "Institution created successfully")
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse("institutions:list")


create_institution_view = CreateInstitutionView.as_view()


@breadcrumb("Edit Institution", parent_url_name="institutions:list")
class UpdateInstitutionView(LoginRequiredMixin, UpdateView[Institution, InstitutionForm]):
    template_name = "institutions/institution_form.html"
    model = Institution
    form_class = InstitutionForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Edit Institution"
        context["link_types"] = InstitutionLinkType.objects.all()
        return context

    def form_valid(self, form: InstitutionForm) -> HttpResponse:
        self.object = form.save()

        InstitutionLink.objects.filter(institution=self.object).delete()

        link_types = self.request.POST.getlist("link_type")
        link_values = self.request.POST.getlist("link_value")

        for type_id, value in zip(link_types, link_values):
            if type_id and value:
                InstitutionLink.objects.create(
                    institution=self.object,
                    type_id=type_id,
                    value=value,
                )

        messages.success(self.request, "Institution updated successfully")
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse("institutions:list")


update_institution_view = UpdateInstitutionView.as_view()


@login_required
def toggle_selectable(request: HttpRequest, pk: int) -> HttpResponse:
    institution = Institution.objects.get(pk=pk)
    institution.virtual = not institution.virtual
    institution.save()
    return HttpResponse()


@login_required
@breadcrumb("Import Institutions", parent_url_name="institutions:list", preserve_filters=True)
def import_view(request: HttpRequest) -> HttpResponse:
    return render(request, "institutions/institution_import.html")


@login_required
@require_POST
def import_from_file(request: HttpRequest) -> HttpResponse:
    uploaded_file = request.FILES["institution-list"]

    if not isinstance(uploaded_file, UploadedFile):
        raise ValueError("No file uploaded")

    with uploaded_file.open() as file:
        services.import_from_file(BytesIO(file.read()))

    messages.success(request, "Institutions imported successfully")
    return redirect("institutions:list")


@login_required
def add_institution_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "institutions/partials/institution_linkrow.html",
        {"link_types": InstitutionLinkType.objects.all()},
    )
