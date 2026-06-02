from datetime import datetime
from io import StringIO
from django.contrib import messages

from django.urls import reverse
import polars as pl
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.views import SimpleSearchEntityListView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from coda.apps.breadcrumbs.decorators import breadcrumb
from django.views.decorators.http import require_GET, require_POST


@breadcrumb("CSV Exports")
class FundingRequestCSVExportListView(
    LoginRequiredMixin, SimpleSearchEntityListView[FundingRequestCSVExport]
):
    model = FundingRequestCSVExport
    # template_name = "export/fundingrequest_csv_list.html"
    context_object_name = "exports"
    paginate_by = 10
    ordering = ["-created_at"]
    entity_name = "Funding Request CSV Export"
    search_fields = ["name"]
    entity_list_item_template = "export/fundingrequest_csv_list_item.html"
    search_placeholder = "Search exports..."
    entity_create_url = "exports:fundingrequests_csv_create"
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"


fundingrequest_csv_export_list_view = FundingRequestCSVExportListView.as_view()


@login_required
@breadcrumb("Generate New Report", parent_url_name="exports:fundingrequests_csv_list")
def fundingrequest_csv_export_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(request, "export/fundingrequest_csv_form.html", context={})

    title = request.POST.get("title", "").strip() or "Unnamed CSV Export"

    try:
        period_start_str = request.POST.get("period_start")
        period_end_str = request.POST.get("period_end")
        if not period_start_str or not period_end_str:
            raise ValueError("Both period_start and period_end are required.")

        period_start = datetime.strptime(period_start_str, "%Y-%m-%d").date()
        period_end = datetime.strptime(period_end_str, "%Y-%m-%d").date()
    except ValueError as e:
        return HttpResponse(f"Invalid date format: {e}", status=400)

    # Keep raw filters for reproducibility. For now, form only contains period fields.
    filters: dict[str, str] = {
        "period_start": period_start_str,
        "period_end": period_end_str,
    }

    # Generate once to calculate row count at creation time; full data is regenerated on demand.
    csv_content = export_fundingrequests_to_csv(period_start, period_end)
    row_count = pl.read_csv(StringIO(csv_content), separator=";").height

    export = FundingRequestCSVExport.objects.create(
        name=title,
        filters=filters,
        record_count=row_count,
    )

    return redirect("exports:fundingrequests_csv_detail", pk=export.pk)


@login_required
@require_GET
@breadcrumb("Export Details", parent_url_name="exports:fundingrequests_csv_list")
def fundingrequest_csv_detail_page(request: HttpRequest, pk: int) -> HttpResponse:
    export = get_object_or_404(FundingRequestCSVExport, pk=pk)

    period_start = datetime.strptime(export.filters["period_start"], "%Y-%m-%d").date()
    period_end = datetime.strptime(export.filters["period_end"], "%Y-%m-%d").date()
    csv_content = export_fundingrequests_to_csv(period_start, period_end)

    preview_columns = [
        "request_id",
        "publication_title",
        "doi",
        "contract_name",
        "invoice_number",
        "position_amount",
    ]
    preview_df = pl.read_csv(StringIO(csv_content), separator=";").select(preview_columns).head(50)
    # preview_rows = preview_df.to_dicts()
    preview_rows = preview_df.rows()
    # preview_columns = preview_df.columns

    return render(
        request,
        "export/fundingrequest_csv_detail.html",
        context={
            "export": export,
            "preview_rows": preview_rows,
            "preview_columns": preview_columns,
        },
    )


@login_required
@require_GET
def fundingrequest_download_csv(request: HttpRequest, pk: int) -> HttpResponse:
    export = get_object_or_404(FundingRequestCSVExport, pk=pk)

    period_start = datetime.strptime(export.filters["period_start"], "%Y-%m-%d").date()
    period_end = datetime.strptime(export.filters["period_end"], "%Y-%m-%d").date()
    csv_content = export_fundingrequests_to_csv(period_start, period_end)

    filename = f"{slugify(export.name) or 'fundingrequest-export'}.csv"
    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


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
