from typing import Any, cast

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.fundingrequests.forms import ExternalFundingFormset, FundingOrganizationLinkForm
from coda.apps.fundingrequests.models import (
    ExternalFunding,
    FundingOrganization,
    FundingOrganizationLinkType,
)
from coda.apps.fundingrequests.services.funder_services import (
    can_delete_funding_organization,
    can_merge_funding_organization,
    delete_funding_organization,
    find_overlapping_organizations,
    merge_funding_organizations,
    search_organizations_for_merge,
    update_funder_from_ror,
)
from coda.apps.views import SimpleSearchEntityListView
from coda.contexts.fundingrequest.services.funder_resolution.ror_client.ror_client import RORClient
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.fundingrequest.organization import preview_merge_funders

FUNDERS_LIST_URL = "fundingrequests:funders"
FUNDER_DETAIL_URL = "fundingrequests:funder_detail"
FUNDER_ENTITY_NAME = "Funding Organization"
FUNDER_ARCHIVE_SUCCESS_MSG = "Funding organization '{name}' archived successfully."
FUNDER_RESTORE_SUCCESS_MSG = "Funding organization '{name}' restored successfully."
FUNDER_DELETE_SUCCESS_MSG = "Funding organization '{name}' deleted successfully."


def get_ror_client() -> RORClient:
    return RORClient()


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
    supports_archiving = True

    def get_entities(self, request: HttpRequest) -> Any:
        search_term = request.GET.get("query", "").strip()
        include_archived = request.GET.get("include_archived") == "on"

        queryset = (
            FundingOrganization.all_objects.all()
            if include_archived
            else FundingOrganization.objects.all()
        )

        if search_term:
            queryset = queryset.filter(name__icontains=search_term)

        return DomainQuerySet(
            queryset.prefetch_related("links").order_by("name"),
            lambda x: cast(FundingOrganization, x),
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "include_archived": self.request.GET.get("include_archived") == "on",
        }


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

    def persist_links(
        self, org: FundingOrganization, link_forms: list[FundingOrganizationLinkForm]
    ) -> bool:
        """Validate link forms and persist to org. Returns True if all valid."""
        for form in link_forms:
            if not form.is_valid():
                return False
        _links = [form.link_object() for form in link_forms]
        links = [link for link in _links if link is not None]
        org.set_links(links)
        return True


@breadcrumb("Funding Organization Detail", parent_url_name=FUNDERS_LIST_URL)
class FundingOrganizationDetailView(LoginRequiredMixin, DetailView[FundingOrganization]):
    model = FundingOrganization
    queryset = FundingOrganization.all_objects.prefetch_related("links")
    template_name = "fundingrequests/funders/detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        funding_records = ExternalFunding.objects.filter(organization=self.object).select_related(
            "funding_request"
        )
        return super().get_context_data(**kwargs) | {
            "funding_records": funding_records,
        }


fundingorganizations_detail = FundingOrganizationDetailView.as_view()


@breadcrumb("Create Funding Organization", parent_url_name=FUNDERS_LIST_URL)
class FundingOrganizationCreateView(
    LoginRequiredMixin,
    FundingOrganizationLinkFormMixin,
    CreateView[FundingOrganization, FundingOrganizationForm],
):
    model = FundingOrganization
    form_class = FundingOrganizationForm
    template_name = "fundingrequests/funders/funder_form.html"
    success_url = reverse_lazy(FUNDERS_LIST_URL)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Funding Organization"
        context["link_types"] = FundingOrganizationLinkType.objects.all()
        context["links"] = self.assemble_link_data() if self.has_links() else []
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        link_forms = self.link_forms()
        for f in link_forms:
            if not f.is_valid():
                return self.form_invalid(form)
        self.object = cast(FundingOrganization, form.save())
        self.persist_links(self.object, link_forms)
        return redirect(self.get_success_url())


fundingorganizations_create = FundingOrganizationCreateView.as_view()


@breadcrumb("Update Funding Organization", parent_url_name=FUNDER_DETAIL_URL)
class FundingOrganizationUpdateView(
    LoginRequiredMixin,
    FundingOrganizationLinkFormMixin,
    UpdateView[FundingOrganization, FundingOrganizationForm],
):
    model = FundingOrganization
    queryset = FundingOrganization.all_objects.all()
    form_class = FundingOrganizationForm
    template_name = "fundingrequests/funders/funder_form.html"
    success_url = reverse_lazy(FUNDERS_LIST_URL)

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
            {"link": {"link_type": link.type(), "link_value": link.value()}, "errors": {}}
            for link in self.object.get_links()
        ]

    def form_valid(self, form: Any) -> HttpResponse:
        self.object = form.save()
        if not self.persist_links(self.object, self.link_forms()):
            return self.form_invalid(form)
        return redirect(self.get_success_url())


fundingorganizations_update = FundingOrganizationUpdateView.as_view()


def _htmx_redirect(url: str) -> HttpResponse:
    response = HttpResponse(status=200)
    response["HX-Redirect"] = url
    return response


def _archive_modal_context(org: FundingOrganization, *, error: str | None = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "org": org,
        "archive_url": reverse("fundingrequests:funder_archive", kwargs={"pk": org.pk}),
    }
    if error:
        ctx["error"] = error
    return ctx


def _restore_modal_context(org: FundingOrganization, *, error: str | None = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "org": org,
        "restore_url": reverse("fundingrequests:funder_restore", kwargs={"pk": org.pk}),
    }
    if error:
        ctx["error"] = error
    return ctx


@login_required
@require_GET
def request_delete_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    can_delete, blocking_reasons = can_delete_funding_organization(org)

    return render(
        request,
        "partials/entity_deletion_modal.html",
        {
            "entity_type": FUNDER_ENTITY_NAME,
            "entity_name": org.name,
            "can_delete": can_delete,
            "blocking_reasons": blocking_reasons,
            "delete_url": reverse("fundingrequests:funder_delete", kwargs={"pk": pk}),
        },
    )


@login_required
@require_POST
def delete_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)

    try:
        delete_funding_organization(org)
    except ValueError as e:
        messages.error(request, str(e))
        return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": pk}))

    messages.success(request, FUNDER_DELETE_SUCCESS_MSG.format(name=org.name))
    return _htmx_redirect(reverse(FUNDERS_LIST_URL))


@login_required
@require_GET
def request_archive_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    return render(
        request, "fundingrequests/funders/archive_modal.html", _archive_modal_context(org)
    )


@login_required
@require_POST
def archive_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    try:
        org.archive()
    except ValueError as e:
        return render(
            request,
            "fundingrequests/funders/archive_modal.html",
            _archive_modal_context(org, error=str(e)),
        )
    messages.success(request, FUNDER_ARCHIVE_SUCCESS_MSG.format(name=org.name))
    return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": pk}))


@login_required
@require_GET
def request_restore_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    return render(
        request, "fundingrequests/funders/restore_modal.html", _restore_modal_context(org)
    )


@login_required
@require_POST
def restore_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    try:
        org.restore()
    except ValueError as e:
        return render(
            request,
            "fundingrequests/funders/restore_modal.html",
            _restore_modal_context(org, error=str(e)),
        )
    messages.success(request, FUNDER_RESTORE_SUCCESS_MSG.format(name=org.name))
    return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": pk}))


@login_required
@require_GET
def fundingorganization_create_modal(request: HttpRequest) -> HttpResponse:
    form = FundingOrganizationForm()

    return render(
        request,
        "partials/entity_creation_modal.html",
        {
            "entity_name": FUNDER_ENTITY_NAME,
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
                "entity_name": FUNDER_ENTITY_NAME,
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


@login_required
@require_GET
def request_update_from_ror_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    return render(
        request,
        "fundingrequests/funders/update_from_ror_modal.html",
        {
            "org": org,
            "update_url": reverse("fundingrequests:funder_update_from_ror", kwargs={"pk": pk}),
        },
    )


@login_required
@require_POST
def update_from_ror_funder(request: HttpRequest, pk: int) -> HttpResponse:
    org = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    try:
        ror_client = get_ror_client()
        links_changed = update_funder_from_ror(FundingOrganizationId(org.pk), ror_client)
        messages.success(
            request, f"Funding organization '{org.name}' updated from ROR successfully."
        )

        # Check for overlapping organizations if links changed
        if links_changed:
            overlapping_orgs = find_overlapping_organizations(org)
            if overlapping_orgs:
                return render(
                    request,
                    "fundingrequests/funders/overlap_detection_dialog.html",
                    {
                        "source": org,
                        "overlapping_orgs": overlapping_orgs,
                    },
                )
    except Exception as e:
        messages.error(request, f"Error updating from ROR: {str(e)}")
    return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": pk}))


@login_required
@require_GET
def merge_funder_select_target(request: HttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    query = request.GET.get("query", "").strip()
    results = []

    if query:
        results = search_organizations_for_merge(query, exclude_pk=source.pk)

    ctx = {"source": source, "query": query, "results": results}
    if query:
        # Search form submission — update content inside existing dialog
        return render(request, "fundingrequests/funders/merge_select_target_content.html", ctx)
    # Initial load — return full dialog wrapper
    return render(request, "fundingrequests/funders/merge_select_target_dialog.html", ctx)


@login_required
@require_GET
def merge_funder_preview(request: HttpRequest, pk: int, target_pk: int) -> HttpResponse:
    source = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    target = get_object_or_404(FundingOrganization.all_objects, pk=target_pk)

    can_merge, reasons = can_merge_funding_organization(source, target)
    if not can_merge:
        messages.error(request, f"Cannot merge organizations: {', '.join(reasons)}")
        return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": pk}))

    # Get affected funding records from both source and target

    affected_records = ExternalFunding.objects.filter(
        organization__in=[source, target]
    ).select_related("funding_request")

    # Calculate merged links
    source_links = source.get_links()
    target_links = target.get_links()
    merged_funder = preview_merge_funders(
        target_name=target.name,
        source_links=source_links,
        target_links=target_links,
    )

    return render(
        request,
        "fundingrequests/funders/merge_preview.html",
        {
            "source": source,
            "target": target,
            "merged_links": merged_funder.links,
            "affected_records": affected_records,
            "execute_url": reverse(
                "fundingrequests:funder_merge_execute",
                kwargs={"pk": pk, "target_pk": target_pk},
            ),
        },
    )


@login_required
@require_POST
def merge_funder_execute(request: HttpRequest, pk: int, target_pk: int) -> HttpResponse:
    source = get_object_or_404(FundingOrganization.all_objects, pk=pk)
    target = get_object_or_404(FundingOrganization.all_objects, pk=target_pk)

    can_merge, reasons = can_merge_funding_organization(source, target)
    if not can_merge:
        messages.error(request, f"Cannot merge organizations: {', '.join(reasons)}")
        return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": pk}))

    try:
        merge_funding_organizations(source, target)
        messages.success(
            request,
            f"Funding organization '{source.name}' merged into '{target.name}' successfully.",
        )
    except Exception as e:
        messages.error(request, f"Error merging organizations: {str(e)}")

    return _htmx_redirect(reverse(FUNDER_DETAIL_URL, kwargs={"pk": target_pk}))
