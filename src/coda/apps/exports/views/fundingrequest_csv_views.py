from typing import Any, cast

from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from coda.apps.breadcrumbs.decorators import breadcrumb
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.exports.services.filter_display import (
    build_applied_filters,
    build_filter_form_context,
    parse_current_filters_to_context,
)
from coda.apps.exports.services.filter_form import (
    FilterCleanedData,
    FormFieldErrors,
    FundingRequestFilterForm,
    current_filters_from_post,
    form_error_lines,
)
from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.exports.views.base_csv_views import (
    csv_delete_view,
    csv_detail_page,
    csv_download_view,
    csv_regen_view,
    save_export_csv_file,
)
from coda.apps.views import SimpleSearchEntityListView
from coda.contexts.exports.dto.filters import ExportFiltersDto

FUNDINGREQUESTS_CSV_CREATE_URL = "exports:fundingrequests_csv_create"
FUNDINGREQUESTS_CSV_LIST_URL = "exports:fundingrequests_csv_list"

PREVIEW_COLUMNS = [
    "request_id",
    "publication_title",
    "doi",
    "contract_name",
    "invoice_number",
    "position_amount",
]


@breadcrumb("Funding Request CSV Export", parent_url_name="exports:export_home")
class FundingRequestCSVExportListView(
    LoginRequiredMixin, SimpleSearchEntityListView[FundingRequestCSVExport]
):
    model = FundingRequestCSVExport
    context_object_name = "exports"
    paginate_by = 10
    ordering = ["-created_at"]
    entity_name = "Funding Request CSV Export"
    search_fields = ["name"]
    entity_list_item_template = "export/fundingrequest_csv_list_item.html"
    search_placeholder = "Search exports..."
    entity_create_url = FUNDINGREQUESTS_CSV_CREATE_URL
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"


fundingrequest_csv_export_list_view = FundingRequestCSVExportListView.as_view()


@login_required
@require_GET
@breadcrumb(
    "CSV Export Details",
    parent_url_name=FUNDINGREQUESTS_CSV_LIST_URL,
)
def fundingrequest_csv_detail_page(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    return csv_detail_page(
        request,
        pk,
        model=FundingRequestCSVExport,
        template_name="export/fundingrequest_csv_detail.html",
        preview_columns=PREVIEW_COLUMNS,
        applied_filters_builder=build_applied_filters,
        create_url_name=FUNDINGREQUESTS_CSV_CREATE_URL,
        regen_url_name="exports:fundingrequests_csv_regen",
    )


@login_required
@require_http_methods(["GET", "POST"])
@breadcrumb(
    "Generate New CSV Export",
    parent_url_name=FUNDINGREQUESTS_CSV_LIST_URL,
)
def fundingrequest_csv_export_create_view(
    request: HttpRequest,
) -> HttpResponse:
    if request.method == "POST":
        form = FundingRequestFilterForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "exports/generate_export_form.html",
                _export_form_context(
                    request,
                    form,
                    form_errors=form_error_lines(form),
                    current_filters=current_filters_from_post(request.POST),
                ),
            )

        cleaned = cast(FilterCleanedData, form.cleaned_data)
        title = cleaned["title"].strip() or "Unnamed CSV Export"
        dto = ExportFiltersDto.from_form_data(cleaned)
        csv_content = export_fundingrequests_to_csv(dto.to_params())

        export = FundingRequestCSVExport.objects.create(
            name=title,
            filters=dto.to_storage(),
            record_count=0,
        )
        save_export_csv_file(export, csv_content)

        return redirect(
            "exports:fundingrequests_csv_detail",
            pk=export.pk,
        )

    return render(
        request,
        "exports/generate_export_form.html",
        _export_form_context(request, FundingRequestFilterForm()),
    )


def _export_form_context(
    request: HttpRequest,
    form: FundingRequestFilterForm,
    form_errors: list[FormFieldErrors] | None = None,
    current_filters: dict[str, str | list[str]] | None = None,
) -> dict[str, object]:
    context = build_filter_form_context()
    context["form"] = form
    context["expand_advanced_search"] = bool(request.GET) or form_errors is not None
    context["current_filters"] = current_filters or parse_current_filters_to_context(request)
    context.update(
        {
            "page_title": "Generate New CSV Export",
            "form_action_url": reverse(FUNDINGREQUESTS_CSV_CREATE_URL),
            "parameters_title": "Export Parameters",
            "title_label": "Title",
            "title_placeholder": "Enter a title for the export",
            "cancel_url": reverse(FUNDINGREQUESTS_CSV_LIST_URL),
            "submit_button_text": "Generate CSV Export",
            "include_payment_status": True,
            "include_decimal_separator": True,
            "show_filters": [
                "publication_type",
                "contract",
                "status",
                "payment_method",
                "open_access_type",
                "publication_state",
                "labels",
                "payment_status",
                "funding_source",
            ],
        }
    )
    if form_errors is not None:
        context["form_errors"] = form_errors
    return context


@login_required
@require_POST
def fundingrequest_csv_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_delete_view(
        request, pk, model=FundingRequestCSVExport, list_url_name=FUNDINGREQUESTS_CSV_LIST_URL
    )


@login_required
@require_GET
def fundingrequest_download_csv(
    request: HttpRequest,
    pk: int,
) -> FileResponse | HttpResponse:
    return csv_download_view(pk, model=FundingRequestCSVExport)


@login_required
@require_POST
def fundingrequest_csv_regen_view(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    return csv_regen_view(
        pk,
        model=FundingRequestCSVExport,
        generate_csv=_generate_csv_from_filters,
        detail_url_name="exports:fundingrequests_csv_detail",
    )


def _generate_csv_from_filters(filters: dict[str, Any]) -> str:
    dto = ExportFiltersDto.model_validate(filters)
    return export_fundingrequests_to_csv(dto.to_params())
