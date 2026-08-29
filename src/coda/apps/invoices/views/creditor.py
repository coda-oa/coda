from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices import repository, services
from coda.apps.search import build_search_filter
from coda.apps.invoices.forms import CreditorForm
from coda.apps.invoices.models import Creditor
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.finance.invoice import CreditorId

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Creditors", parent_url_name="invoices:finances_home")
class CreditorListView(LoginRequiredMixin, SimpleSearchEntityListView[Creditor]):
    model = Creditor
    paginate_by = 10
    entity_name = "Creditors"
    entity_create_url = "invoices:creditor_create"
    entity_list_item_template = "invoices/creditors/list.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True
    supports_archiving = True

    def get_entities(self, request: HttpRequest) -> Any:
        search_term = request.GET.get("query", "").strip()
        include_archived = request.GET.get("include_archived") == "on"

        queryset = Creditor.all_objects.all() if include_archived else Creditor.objects.all()

        if search_term:
            queryset = queryset.filter(build_search_filter(search_term, "name"))

        return DomainQuerySet(queryset.order_by("name"), lambda x: cast(Creditor, x))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "include_archived": self.request.GET.get("include_archived") == "on",
        }


@breadcrumb("Creditor Detail", parent_url_name="invoices:creditor_list")
class CreditorDetailView(LoginRequiredMixin, DetailView[Creditor]):
    model = Creditor
    queryset = Creditor.all_objects.all()
    template_name = "invoices/creditors/detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        invoices = repository.get_by_creditor(CreditorId(self.object.id))

        return super().get_context_data(**kwargs) | {"creditor": self.object, "invoices": invoices}


@breadcrumb("Create Creditor", parent_url_name="invoices:creditor_list")
class CreditorCreateView(LoginRequiredMixin, CreateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = ["name"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Creditor"}


@breadcrumb("Edit Creditor", parent_url_name="invoices:creditor_detail")
class CreditorUpdateView(LoginRequiredMixin, UpdateView[Creditor, CreditorForm]):
    model = Creditor
    queryset = Creditor.all_objects.all()
    template_name = "generic_form_view.html"
    fields = ["name"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Edit Creditor"}


def _htmx_redirect(url: str) -> HttpResponse:
    response = HttpResponse(status=200)
    response["HX-Redirect"] = url
    return response


@login_required
@require_GET
def request_delete_creditor(request: HttpRequest, pk: int) -> HttpResponse:
    creditor = get_object_or_404(Creditor.all_objects, pk=pk)
    can_delete, blocking_reasons = services.can_delete_creditor(creditor)

    return render(
        request,
        "partials/entity_deletion_modal.html",
        {
            "entity_type": "Creditor",
            "entity_name": creditor.name,
            "can_delete": can_delete,
            "blocking_reasons": blocking_reasons,
            "delete_url": reverse("invoices:creditor_delete", kwargs={"pk": pk}),
        },
    )


@login_required
@require_POST
def delete_creditor(request: HttpRequest, pk: int) -> HttpResponse:
    creditor = get_object_or_404(Creditor.all_objects, pk=pk)

    if creditor.archived_at:
        messages.error(request, "Cannot delete archived creditors.")
        return _htmx_redirect(reverse("invoices:creditor_detail", kwargs={"pk": pk}))

    can_delete, blocking_reasons = services.can_delete_creditor(creditor)

    if not can_delete:
        messages.error(request, f"Cannot delete creditor: {', '.join(blocking_reasons)}")
        return _htmx_redirect(reverse("invoices:creditor_detail", kwargs={"pk": pk}))

    creditor_name = creditor.name
    creditor.delete()
    messages.success(request, f"Creditor '{creditor_name}' deleted successfully.")

    return _htmx_redirect(reverse("invoices:creditor_list"))


@login_required
@require_GET
def request_archive_creditor(request: HttpRequest, pk: int) -> HttpResponse:
    creditor = get_object_or_404(Creditor.all_objects, pk=pk)

    return render(
        request,
        "invoices/creditors/archive_modal.html",
        {
            "creditor": creditor,
            "archive_url": reverse("invoices:creditor_archive", kwargs={"pk": pk}),
        },
    )


@login_required
@require_POST
def archive_creditor(request: HttpRequest, pk: int) -> HttpResponse:
    creditor = get_object_or_404(Creditor.all_objects, pk=pk)

    try:
        services.archive_creditor(creditor)
    except ValueError as e:
        return render(
            request,
            "invoices/creditors/archive_modal.html",
            {
                "creditor": creditor,
                "archive_url": reverse("invoices:creditor_archive", kwargs={"pk": pk}),
                "error": str(e),
            },
        )

    creditor_name = creditor.name
    messages.success(request, f"Creditor '{creditor_name}' archived successfully.")

    return _htmx_redirect(reverse("invoices:creditor_detail", kwargs={"pk": pk}))


@login_required
@require_GET
def request_restore_creditor(request: HttpRequest, pk: int) -> HttpResponse:
    creditor = get_object_or_404(Creditor.all_objects, pk=pk)

    return render(
        request,
        "invoices/creditors/restore_modal.html",
        {
            "creditor": creditor,
            "restore_url": reverse("invoices:creditor_restore", kwargs={"pk": pk}),
        },
    )


@login_required
@require_POST
def restore_creditor(request: HttpRequest, pk: int) -> HttpResponse:
    creditor = get_object_or_404(Creditor.all_objects, pk=pk)

    try:
        services.restore_creditor(creditor)
    except ValueError as e:
        return render(
            request,
            "invoices/creditors/restore_modal.html",
            {
                "creditor": creditor,
                "restore_url": reverse("invoices:creditor_restore", kwargs={"pk": pk}),
                "error": str(e),
            },
        )

    creditor_name = creditor.name
    messages.success(request, f"Creditor '{creditor_name}' restored successfully.")

    return _htmx_redirect(reverse("invoices:creditor_detail", kwargs={"pk": pk}))
