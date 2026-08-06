from io import StringIO
from django.contrib import messages

from django.urls import reverse
import polars as pl
from django.core.files.base import ContentFile
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
import os

from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchParams
from coda.apps.views import SimpleSearchEntityListView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from coda.apps.breadcrumbs.decorators import breadcrumb
from django.views.decorators.http import require_GET, require_POST

from coda.apps.exports.services.filter_display import (
    build_applied_filters,
    build_filter_form_context,
    build_filters_from_request,
    parse_common_filter_fields,
    create_redo_url,
    parse_current_filters_to_context,
)

FUNDINGREQUESTS_CSV_CREATE_URL = "exports:fundingrequests_csv_create"


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
    parent_url_name="exports:fundingrequests_csv_list",
)
def fundingrequest_csv_detail_page(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:

    export = get_object_or_404(
        FundingRequestCSVExport,
        pk=pk,
    )

    applied_filters = build_applied_filters(export.filters)
    redo_url = create_redo_url(export.filters, "exports:fundingrequests_csv_create")

    file_missing = not export.csv_file or not os.path.exists(export.csv_file.path)
    if file_missing:
        return render(
            request,
            "export/fundingrequest_csv_detail.html",
            {
                "export": export,
                "file_missing": True,
                "regen_url": reverse("exports:fundingrequests_csv_regen", args=[export.pk]),
                "applied_filters": applied_filters,
                "redo_url": redo_url,
            },
        )

    preview_df = _create_preview_dataframe(export.csv_file.open("rb").read().decode("utf-8"))

    return render(
        request,
        "export/fundingrequest_csv_detail.html",
        {
            "export": export,
            "file_missing": False,
            "preview_columns": preview_df.columns,
            "preview_rows": preview_df.rows(),
            "applied_filters": applied_filters,
            "redo_url": redo_url,
        },
    )


@login_required
@breadcrumb(
    "Generate New CSV Export",
    parent_url_name="exports:fundingrequests_csv_list",
)
def fundingrequest_csv_export_create_view(
    request: HttpRequest,
) -> HttpResponse:

    if request.method == "GET":
        context = _get_export_form_context()
        context["expand_advanced_search"] = bool(request.GET)
        context["current_filters"] = parse_current_filters_to_context(request)
        context.update(
            {
                "page_title": "Generate New CSV Export",
                "form_action_url": reverse(FUNDINGREQUESTS_CSV_CREATE_URL),
                "parameters_title": "Export Parameters",
                "title_label": "Title",
                "title_placeholder": "Enter a title for the export",
                "cancel_url": reverse("exports:fundingrequests_csv_list"),
                "submit_button_text": "Generate CSV Export",
                "include_payment_status": True,
            }
        )

        return render(
            request,
            "exports/generate_export_form.html",
            context=context,
        )

    title = request.POST.get("title", "").strip() or "Unnamed CSV Export"

    filters = _build_export_filters(request)
    csv_content = _generate_csv_from_filters(filters)

    export = FundingRequestCSVExport.objects.create(
        name=title,
        filters=filters,
        record_count=0,
    )
    _save_csv_file(export, csv_content)

    return redirect(
        "exports:fundingrequests_csv_detail",
        pk=export.pk,
    )


@login_required
@require_POST
def fundingrequests_csv_delete(request: HttpRequest, pk: int) -> HttpResponse:
    export = get_object_or_404(FundingRequestCSVExport, pk=pk)
    export_title = export.name
    export.delete()
    messages.success(request, f"CSV export '{export_title}' deleted successfully.")

    response = HttpResponse(status=200)
    response["HX-Redirect"] = reverse("exports:fundingrequests_csv_list")
    return response


@login_required
@require_GET
def fundingrequest_download_csv(
    request: HttpRequest,
    pk: int,
) -> FileResponse | HttpResponse:

    export = get_object_or_404(
        FundingRequestCSVExport,
        pk=pk,
    )

    if not export.csv_file or not os.path.exists(export.csv_file.path):
        return HttpResponse(status=404)

    return FileResponse(export.csv_file.open("rb"))


@login_required
@require_POST
def fundingrequest_csv_regen_view(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:

    export = get_object_or_404(
        FundingRequestCSVExport,
        pk=pk,
    )

    csv_content = _generate_csv_from_filters(export.filters)
    _save_csv_file(export, csv_content)

    return redirect(
        "exports:fundingrequests_csv_detail",
        pk=export.pk,
    )


# helpers


def _save_csv_file(export: FundingRequestCSVExport, csv_content: str) -> None:
    row_count = pl.read_csv(StringIO(csv_content), separator=";").height
    filename = f"{slugify(export.name) or 'export'}-{export.id}.csv"
    export.csv_file.save(filename, ContentFile(csv_content.encode("utf-8")))
    export.record_count = row_count
    export.save(update_fields=["record_count"])


def _parse_filter_dict(filters: dict[str, str]) -> FundingRequestSearchParams:
    """Parse filter dict into a FundingRequestSearchParams object."""
    return parse_common_filter_fields(filters)


def _create_preview_dataframe(
    csv_content: str,
) -> pl.DataFrame:

    preview_columns = [
        "request_id",
        "publication_title",
        "doi",
        "contract_name",
        "invoice_number",
        "position_amount",
    ]

    return (
        pl.read_csv(
            StringIO(csv_content),
            separator=";",
        )
        .select(preview_columns)
        .head(50)
    )


def _build_export_filters(request: HttpRequest) -> dict[str, str]:
    return build_filters_from_request(request)


def _get_export_form_context() -> dict[str, object]:
    return build_filter_form_context()


def _generate_csv_from_filters(filters: dict[str, str]) -> str:
    params = _parse_filter_dict(filters)
    return export_fundingrequests_to_csv(params)
