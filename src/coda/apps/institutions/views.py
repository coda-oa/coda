from datetime import datetime
from io import BytesIO
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.uploadedfile import UploadedFile
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import CreateView, UpdateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.institutions import services, repository
from coda.apps.institutions.forms import InstitutionForm, InstitutionLinkForm
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.views import SimpleSearchEntityListView

INSTITUTION_IMPORT_VIEW_URL = "institutions:import_view"


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
            if link_data["link_type"] and link_data["link_value"]:
                link_type = InstitutionLinkType.objects.get(name=link_data["link_type"])
                InstitutionLink.objects.create(
                    institution=institution,
                    type=link_type,
                    value=link_data["link_value"],
                )
        return True


@breadcrumb("Organization Structure")
class InstitutionListView(LoginRequiredMixin, SimpleSearchEntityListView[Institution]):
    model = Institution
    template_name = "institutions/institution_list.html"
    entity_name = "Organization Structure"
    entity_list_item_template = "institutions/institution_list_item.html"
    entity_create_url = "institutions:create"
    entity_secondary_create_url = INSTITUTION_IMPORT_VIEW_URL
    use_generic_entity_filter = True
    supports_archiving = True
    search_placeholder = "Search institutions..."

    def get_entities(self, request: HttpRequest) -> Any:
        search_term = request.GET.get("query", "").strip()
        include_archived = request.GET.get("include_archived") == "on"

        qs = repository.search(
            name=search_term if search_term else None, include_archived=include_archived
        )
        return DomainQuerySet(qs, lambda x: x)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "entity_secondary_create_url": self.entity_secondary_create_url,
            "include_archived": self.request.GET.get("include_archived") == "on",
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

    def get_queryset(self) -> QuerySet[Institution]:
        return Institution.all_objects.all()

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
                {"link": {"link_type": link.type.name, "link_value": link.value}, "errors": {}}
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
@breadcrumb("Institution Detail", parent_url_name="institutions:list")
def institution_detail(request: HttpRequest, pk: int) -> HttpResponse:
    institution = get_object_or_404(Institution.all_objects, pk=pk)
    relationships = services.get_institution_relationships(institution)
    can_delete, blocking_reasons = services.can_delete_institution(institution)

    return render(
        request,
        "institutions/institution_detail.html",
        {
            "institution": institution,
            "relationships": relationships,
            "can_delete": can_delete,
            "blocking_reasons": blocking_reasons,
        },
    )


def request_set_successor(request: HttpRequest, pk: int) -> HttpResponse:
    institution = get_object_or_404(Institution.objects, pk=pk)
    available_institutions = Institution.objects.exclude(pk=pk).order_by("name")

    is_home_institution = GlobalPreferences.objects.filter(home_institution=institution).exists()
    has_children = institution.children.exists()

    return render(
        request,
        "institutions/institution_successor_modal.html",
        {
            "institution": institution,
            "available_institutions": available_institutions,
            "is_home_institution": is_home_institution,
            "has_children": has_children,
        },
    )


def request_delete_institution(request: HttpRequest, pk: int) -> HttpResponse:
    institution = get_object_or_404(Institution.objects, pk=pk)

    return render(
        request,
        "partials/entity_deletion_modal.html",
        {
            "entity_type": "Institution",
            "entity_name": institution.name,
            "delete_url": reverse("institutions:delete", kwargs={"pk": pk}),
        },
    )


def _archive_no_successor(request: HttpRequest, institution: Institution) -> HttpResponse:
    services.archive_without_successor(institution)
    messages.success(request, f"Institution '{institution.name}' archived successfully.")
    return _htmx_redirect(reverse("institutions:detail", kwargs={"pk": institution.pk}))


def _archive_with_new_successor(request: HttpRequest, institution: Institution) -> HttpResponse:
    successor_name = request.POST.get("new_name", "").strip()
    if not successor_name:
        # Re-render modal with error
        return _render_successor_modal_with_errors(
            request, institution, errors={"new_name": "New institution name is required."}
        )

    successor = services.archive_and_create_successor(institution, successor_name=successor_name)
    messages.success(request, f"Institution archived and succeeded by {successor.name}.")
    return _htmx_redirect(reverse("institutions:detail", kwargs={"pk": successor.pk}))


def _archive_with_existing_successor(
    request: HttpRequest, institution: Institution
) -> HttpResponse:
    successor_id = request.POST.get("successor_id")
    if not successor_id:
        return _render_successor_modal_with_errors(
            request, institution, errors={"successor_id": "Please select a successor institution."}
        )

    try:
        successor = Institution.objects.get(pk=successor_id)
    except Institution.DoesNotExist:
        return _render_successor_modal_with_errors(
            request,
            institution,
            errors={"successor_id": "Selected successor institution not found."},
        )

    services.archive_with_existing_successor(institution, [successor])
    messages.success(request, f"Institution archived and succeeded by {successor.name}.")
    return _htmx_redirect(reverse("institutions:detail", kwargs={"pk": institution.pk}))


def _render_successor_modal_with_errors(
    request: HttpRequest,
    institution: Institution,
    errors: dict[str, str] | None = None,
    general_error: str | None = None,
) -> HttpResponse:
    available_institutions = Institution.objects.exclude(pk=institution.pk).order_by("name")
    is_home_institution = GlobalPreferences.objects.filter(home_institution=institution).exists()
    has_children = institution.children.exists()

    return render(
        request,
        "institutions/institution_successor_modal.html",
        {
            "institution": institution,
            "available_institutions": available_institutions,
            "is_home_institution": is_home_institution,
            "has_children": has_children,
            "errors": errors or {},
            "general_error": general_error,
            "form_data": request.POST,
        },
    )


@login_required
@require_POST
def set_successor(request: HttpRequest, pk: int) -> HttpResponse:
    institution = get_object_or_404(Institution.all_objects, pk=pk)

    if institution.archived_at:
        return _render_successor_modal_with_errors(
            request, institution, general_error="Institution is already archived."
        )

    successor_handlers = {
        "no_successor": _archive_no_successor,
        "create_new": _archive_with_new_successor,
        "select_existing": _archive_with_existing_successor,
    }

    successor_type = request.POST.get("successor_type") or ""
    handler = successor_handlers.get(successor_type)

    if not handler:
        return _render_successor_modal_with_errors(
            request, institution, general_error="Invalid successor type."
        )

    try:
        return handler(request, institution)
    except ValueError as e:
        return _render_successor_modal_with_errors(request, institution, general_error=str(e))


def _htmx_redirect(url: str) -> HttpResponse:
    response = HttpResponse(status=200)
    response["HX-Redirect"] = url
    return response


@login_required
@require_POST
def delete_institution(request: HttpRequest, pk: int) -> HttpResponse:
    institution = get_object_or_404(Institution.all_objects, pk=pk)

    # Cannot delete archived institutions
    if institution.archived_at:
        messages.error(request, "Cannot delete archived institutions.")
        return _htmx_redirect(reverse("institutions:detail", kwargs={"pk": pk}))

    # Check if can delete
    can_delete, blocking_reasons = services.can_delete_institution(institution)

    if not can_delete:
        messages.error(request, f"Cannot delete institution: {', '.join(blocking_reasons)}")
        return _htmx_redirect(reverse("institutions:detail", kwargs={"pk": pk}))

    # Delete the institution
    institution_name = institution.name
    institution.delete()
    messages.success(request, f"Institution '{institution_name}' deleted successfully.")

    return _htmx_redirect(reverse("institutions:list"))


@login_required
def toggle_selectable(request: HttpRequest, pk: int) -> HttpResponse:
    institution = Institution.all_objects.get(pk=pk)
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
    if "institution-list" not in request.FILES:
        messages.error(request, "No file was uploaded. Please select a file to import.")
        return redirect(INSTITUTION_IMPORT_VIEW_URL)

    uploaded_file = request.FILES["institution-list"]

    if not isinstance(uploaded_file, UploadedFile):
        messages.error(request, "Invalid file upload. Please try again.")
        return redirect(INSTITUTION_IMPORT_VIEW_URL)

    try:
        with uploaded_file.open() as file:
            result = services.import_from_file(BytesIO(file.read()))
    except UnicodeDecodeError:
        messages.error(
            request,
            "The uploaded file has an invalid encoding. Please ensure the file is UTF-8 encoded.",
        )
        return redirect(INSTITUTION_IMPORT_VIEW_URL)
    except Exception as e:
        messages.error(
            request,
            f"Failed to import file: {str(e)}. Please check that the file is a valid CSV with the correct format.",
        )
        return redirect(INSTITUTION_IMPORT_VIEW_URL)

    if result.fully_imported == result.total:
        messages.success(request, f"{result.total} institutions imported successfully")
    elif result.partially_imported > 0:
        messages.warning(
            request,
            f"{result.fully_imported} institutions imported successfully, "
            f"{result.partially_imported} with incomplete data (invalid identifiers skipped)",
        )

    if result.errors:
        error_summary = f"{len(result.errors)} validation error(s): <br>"
        error_list_items = "".join(
            [f"<li>{err.institution_name}: {err.message}</li>" for err in result.errors]
        )
        error_html = f"{error_summary}<br><ul class='error'>{error_list_items}</ul>"

        messages.error(request, mark_safe(error_html))

    return redirect("institutions:list")


@login_required
@require_POST
def add_institution_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "partials/linkrow.html",
        {"link_types": InstitutionLinkType.objects.all()},
    )


@login_required
@require_GET
def export_institutions(request: HttpRequest) -> HttpResponse:
    csv_content = services.export_to_csv()
    response = HttpResponse(csv_content, content_type="text/csv")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"institutions_export_{timestamp}.csv"
    response["Content-Disposition"] = f"attachment; filename={filename}"

    return response
