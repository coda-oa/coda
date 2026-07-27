from datetime import datetime
from io import StringIO

import polars as pl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.exports.models import ContractCSVExport
from coda.apps.exports.services.contract_csv.export_service import export_contract_to_csv
from coda.apps.exports.services.filter_display import (
    build_applied_filters_for_contract,
    build_filter_form_context,
    create_redo_url,
    invoice_payment_status_choices,
)
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId, PaymentStatus

CONTRACTS_CSV_CREATE_URL = "exports:contracts_csv_create"


@breadcrumb("Contract CSV Export", parent_url_name="exports:export_home")
class ContractCSVExportListView(LoginRequiredMixin, SimpleSearchEntityListView[ContractCSVExport]):
    model = ContractCSVExport
    context_object_name = "exports"
    paginate_by = 10
    ordering = ["-created_at"]
    entity_name = "Contract CSV Export"
    search_fields = ["name"]
    entity_list_item_template = "export/contract_csv_list_item.html"
    search_placeholder = "Search exports..."
    entity_create_url = CONTRACTS_CSV_CREATE_URL
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"


contract_csv_export_list_view = ContractCSVExportListView.as_view()


@login_required
@require_GET
@breadcrumb(
    "CSV Export Details",
    parent_url_name="exports:contracts_csv_list",
)
def contract_csv_detail_page(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:

    export = get_object_or_404(
        ContractCSVExport,
        pk=pk,
    )

    preview_df = _create_preview_dataframe(export.csv_file.open("rb").read().decode("utf-8"))

    applied_filters = build_applied_filters_for_contract(export.filters)
    redo_url = create_redo_url(export.filters, "exports:contracts_csv_create")

    return render(
        request,
        "export/contract_csv_detail.html",
        {
            "export": export,
            "preview_columns": preview_df.columns,
            "preview_rows": preview_df.rows(),
            "applied_filters": applied_filters,
            "redo_url": redo_url,
        },
    )


@login_required
@breadcrumb(
    "Generate New CSV Export",
    parent_url_name="exports:contracts_csv_list",
)
def contract_csv_export_create_view(
    request: HttpRequest,
) -> HttpResponse:

    if request.method == "GET":
        context = build_filter_form_context()
        context["expand_advanced_search"] = bool(request.GET)
        context.update(
            {
                "page_title": "Generate Contract CSV Export",
                "form_action_url": reverse(CONTRACTS_CSV_CREATE_URL),
                "parameters_title": "Invoice Filter Parameters",
                "title_label": "Title",
                "title_placeholder": "Enter a title for the export",
                "cancel_url": reverse("exports:contracts_csv_list"),
                "submit_button_text": "Generate CSV Export",
                "show_filters": ["payment_status", "funding_source"],
                "payment_status_choices": invoice_payment_status_choices,
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
    row_count = pl.read_csv(
        StringIO(csv_content),
        separator=";",
    ).height

    export = ContractCSVExport.objects.create(
        name=title,
        filters=filters,
        record_count=row_count,
    )

    filename = f"{slugify(title) or 'export'}-{export.id}.csv"

    export.csv_file.save(
        filename,
        ContentFile(csv_content.encode("utf-8")),
    )

    return redirect(
        "exports:contracts_csv_detail",
        pk=export.pk,
    )


@login_required
@require_POST
def contracts_csv_delete(request: HttpRequest, pk: int) -> HttpResponse:
    export = get_object_or_404(ContractCSVExport, pk=pk)
    export_title = export.name
    export.delete()
    messages.success(request, f"CSV export '{export_title}' deleted successfully.")

    response = HttpResponse(status=200)
    response["HX-Redirect"] = reverse("exports:contracts_csv_list")
    return response


@login_required
@require_GET
def contract_download_csv(
    request: HttpRequest,
    pk: int,
) -> FileResponse:

    export = get_object_or_404(
        ContractCSVExport,
        pk=pk,
    )
    return FileResponse(export.csv_file.open("rb"))


# helpers


def _create_preview_dataframe(
    csv_content: str,
) -> pl.DataFrame:

    preview_columns = [
        "contract_name",
        "invoice_number",
        "position_amount",
        "funded_amount",
        "funding_source_name",
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
    filters: dict[str, str] = {
        "period_start": request.POST["period_start"],
        "period_end": request.POST["period_end"],
    }

    for field in ("payment_status", "funding_source"):
        values = [v for v in request.POST.getlist(field) if v]
        if values:
            filters[field] = ",".join(values)

    return filters


def _parse_contract_filter_dict(filters: dict[str, str]) -> InvoiceSearchParams:
    date_range = None
    start_str = filters.get("period_start")
    end_str = filters.get("period_end")
    if start_str and end_str:
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
            date_range = DateRange(start, end)
        except ValueError:
            pass

    payment_status = None
    ps_raw = filters.get("payment_status", "")
    if ps_raw:
        statuses = [s.strip() for s in ps_raw.split(",") if s]
        if statuses:
            payment_status = PaymentStatus(statuses[0])

    funding_source = None
    fs_raw = filters.get("funding_source", "")
    if fs_raw:
        funding_source = FundingSourceId(int(fs_raw))

    return InvoiceSearchParams(
        date_range=date_range,
        payment_status=payment_status,
        funding_source=funding_source,
    )


def _generate_csv_from_filters(filters: dict[str, str]) -> str:
    params = _parse_contract_filter_dict(filters)
    return export_contract_to_csv(params)
