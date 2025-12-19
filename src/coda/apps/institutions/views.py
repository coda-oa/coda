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
from coda.apps.institutions.forms import InstitutionForm, InstitutionLinkForm
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.views import SimpleSearchEntityListView


class InstitutionLinkFormMixin:
    """Mixin to handle institution link forms validation and rendering."""

    request: HttpRequest  # Type hint for mixin

    def has_links(self) -> bool:
        return bool(self.request.POST.get("link_type") and self.request.POST.get("link_value"))

    def assemble_link_data(self) -> list[dict[str, Any]]:
        forms = self.link_forms()
        for form in forms:
            form.full_clean()
        return [{"link": form.get_form_data(), "errors": form.errors} for form in forms]

    def link_forms(self) -> list[InstitutionLinkForm]:
        types = self.request.POST.getlist("link_type")
        values = self.request.POST.getlist("link_value")
        return [
            InstitutionLinkForm({"link_type": link_type, "link_value": link_value})
            for link_type, link_value in zip(types, values)
        ]

    def validate_and_save_links(self, institution: Institution) -> bool:
        """Validate link forms and save them. Returns True if all valid, False otherwise."""
        link_forms = self.link_forms()
        for link_form in link_forms:
            if not link_form.is_valid():
                return False

        for link_form in link_forms:
            link_data = link_form.get_form_data()
            if link_data["type_id"] and link_data["value"]:
                InstitutionLink.objects.create(
                    institution=institution,
                    type_id=link_data["type_id"],
                    value=link_data["value"],
                )
        return True


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
class CreateInstitutionView(
    LoginRequiredMixin, InstitutionLinkFormMixin, CreateView[Institution, InstitutionForm]
):
    template_name = "institutions/institution_form.html"
    model = Institution
    form_class = InstitutionForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Institution"
        context["link_types"] = InstitutionLinkType.objects.all()
        context["links"] = self.assemble_link_data() if self.has_links() else []
        return context

    def form_valid(self, form: InstitutionForm) -> HttpResponse:
        self.object = form.save()

        if not self.validate_and_save_links(self.object):
            return self.form_invalid(form)

        messages.success(self.request, "Institution created successfully")
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse("institutions:list")


create_institution_view = CreateInstitutionView.as_view()


@breadcrumb("Edit Institution", parent_url_name="institutions:list")
class UpdateInstitutionView(
    LoginRequiredMixin, InstitutionLinkFormMixin, UpdateView[Institution, InstitutionForm]
):
    template_name = "institutions/institution_form.html"
    model = Institution
    form_class = InstitutionForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Edit Institution"
        context["link_types"] = InstitutionLinkType.objects.all()
        context["links"] = self._get_links_for_context()
        return context

    def _get_links_for_context(self) -> list[dict[str, Any]]:
        """Get links with errors for POST or existing links for GET."""
        if self.has_links():
            return self.assemble_link_data()
        elif self.object:
            return [
                {"link": {"type_id": link.type_id, "value": link.value}, "errors": {}}
                for link in self.object.links.all()
            ]
        return []

    def form_valid(self, form: InstitutionForm) -> HttpResponse:
        self.object = form.save()

        # Delete existing links and recreate
        InstitutionLink.objects.filter(institution=self.object).delete()

        if not self.validate_and_save_links(self.object):
            return self.form_invalid(form)

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
@require_POST
def add_institution_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "institutions/partials/institution_linkrow.html",
        {"link_types": InstitutionLinkType.objects.all()},
    )
