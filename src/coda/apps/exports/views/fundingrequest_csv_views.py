from collections.abc import Sequence
from io import StringIO
from typing import Any, cast

import polars as pl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django_htmx.http import HttpResponseClientRedirect

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.exports.services.filter_display import (
    build_applied_filters,
    build_filter_form_context,
    create_redo_url,
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
    CsvExportResult,
    export_fundingrequests_to_csv,
)
from coda.apps.search import words_icontains
from coda.apps.views import SimpleSearchEntityListView
from coda.contexts.exports.dto.filters import ExportFiltersDto

FUNDINGREQUESTS_CSV_CREATE_URL = "exports:fundingrequests_csv_create"
CSV_ENCODING = "utf-8-sig"


@breadcrumb("Funding Request CSV Export", parent_url_name="exports:export_home")
class FundingRequestCSVExportListView(
    LoginRequiredMixin, SimpleSearchEntityListView[FundingRequestCSVExport]
):
    model = FundingRequestCSVExport
    context_object_name = "exports"
    paginate_by = 10
    ordering = ["-created_at"]  # noqa: RUF012
    entity_name = "Funding Request CSV Export"
    search_fields = ["name"]  # noqa: RUF012
    entity_list_item_template = "export/fundingrequest_csv_list_item.html"
    search_placeholder = "Search exports..."
    entity_create_url = FUNDINGREQUESTS_CSV_CREATE_URL
    use_generic_entity_filter = True

    def get_entities(self, request: HttpRequest) -> Sequence[FundingRequestCSVExport]:
        search_term = request.GET.get("query", "").strip()
        queryset = FundingRequestCSVExport.objects.defer("csv_content")

        if search_term:
            queryset = queryset.filter(words_icontains(search_term, *self.search_fields))

        order_by = self.ordering or self.search_fields
        return DomainQuerySet(queryset.order_by(*order_by), lambda x: x)


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

    content_missing = not export.csv_content
    if content_missing:
        return render(
            request,
            "export/fundingrequest_csv_detail.html",
            {
                "export": export,
                "content_missing": True,
                "regen_url": reverse("exports:fundingrequests_csv_regen", args=[export.pk]),
                "applied_filters": applied_filters,
                "redo_url": redo_url,
            },
        )

    preview_df = _create_preview_dataframe(export.csv_content)

    return render(
        request,
        "export/fundingrequest_csv_detail.html",
        {
            "export": export,
            "content_missing": False,
            "preview_columns": preview_df.columns,
            "preview_rows": preview_df.rows(),
            "applied_filters": applied_filters,
            "redo_url": redo_url,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@breadcrumb(
    "Generate New CSV Export",
    parent_url_name="exports:fundingrequests_csv_list",
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
        result = export_fundingrequests_to_csv(dto)

        export = FundingRequestCSVExport.objects.create(
            name=title,
            filters=dto.to_storage(),
            record_count=result.row_count,
            csv_content=result.content,
        )

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
            "cancel_url": reverse("exports:fundingrequests_csv_list"),
            "submit_button_text": "Generate CSV Export",
            "include_payment_status": True,
            "include_decimal_separator": True,
        }
    )
    if form_errors is not None:
        context["form_errors"] = form_errors
    return context


@login_required
@require_POST
def fundingrequests_csv_delete(request: HttpRequest, pk: int) -> HttpResponse:
    export = get_object_or_404(FundingRequestCSVExport.objects.defer("csv_content"), pk=pk)
    export_title = export.name
    export.delete()
    messages.success(request, f"CSV export '{export_title}' deleted successfully.")

    return HttpResponseClientRedirect(reverse("exports:fundingrequests_csv_list"))


@login_required
@require_GET
def fundingrequest_download_csv(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    export = get_object_or_404(
        FundingRequestCSVExport,
        pk=pk,
    )

    if not export.csv_content:
        return HttpResponse(status=404)

    response = HttpResponse(
        export.csv_content.encode(CSV_ENCODING),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = content_disposition_header(
        True, _csv_download_filename(export)
    )
    return response


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

    result = _generate_csv_from_filters(export.filters)
    export.csv_content = result.content
    export.record_count = result.row_count
    export.save(update_fields=["csv_content", "record_count"])

    return redirect(
        "exports:fundingrequests_csv_detail",
        pk=export.pk,
    )


def _csv_download_filename(export: FundingRequestCSVExport) -> str:
    return f"{slugify(export.name) or 'export'}-{export.id}.csv"


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


def _generate_csv_from_filters(filters: dict[str, Any]) -> CsvExportResult:
    dto = ExportFiltersDto.model_validate(filters)
    return export_fundingrequests_to_csv(dto)
