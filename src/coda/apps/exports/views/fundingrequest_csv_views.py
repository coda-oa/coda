from datetime import date, datetime
from io import StringIO
from typing import Any
from django.contrib import messages

from django.urls import reverse
import polars as pl
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from dataclasses import asdict, dataclass

from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.fundingrequests.models import Label
from coda.apps.views import SimpleSearchEntityListView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from coda.apps.breadcrumbs.decorators import breadcrumb
from django.views.decorators.http import require_GET, require_POST
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState

_payment_status_choices = [
    ("paid", "Paid"),
    ("unpaid", "Unpaid"),
    ("invoice_received", "Invoice Received"),
    ("covered_by_contract", "Covered by Contract"),
]

_publication_state_choices = [
    ("Published", "Published"),
    *((s.name, s.value) for s in UnpublishedState),
]


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
@require_GET
@breadcrumb(
    "Export Details",
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

    csv_content = _generate_csv_for_export(export)

    preview_df = _create_preview_dataframe(csv_content)

    return render(
        request,
        "export/fundingrequest_csv_detail.html",
        {
            "export": export,
            "preview_columns": preview_df.columns,
            "preview_rows": preview_df.rows(),
        },
    )


@login_required
@breadcrumb(
    "Generate New Report",
    parent_url_name="exports:fundingrequests_csv_list",
)
def fundingrequest_csv_export_create_view(
    request: HttpRequest,
) -> HttpResponse:

    if request.method == "GET":
        return render(
            request,
            "export/fundingrequest_csv_form.html",
            context=_get_export_form_context(),
        )

    title = request.POST.get("title", "").strip() or "Unnamed CSV Export"

    filters = _build_export_filters(request)
    csv_content = _generate_csv_from_filters(filters)
    row_count = pl.read_csv(
        StringIO(csv_content),
        separator=";",
    ).height

    export = FundingRequestCSVExport.objects.create(
        name=title,
        filters=filters,
        record_count=row_count,
    )

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
) -> HttpResponse:

    export = get_object_or_404(
        FundingRequestCSVExport,
        pk=pk,
    )

    csv_content = _generate_csv_for_export(export)

    filename = f"{slugify(export.name) or 'fundingrequest-export'}.csv"

    response = HttpResponse(
        csv_content,
        content_type="text/csv; charset=utf-8",
    )

    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


# helpers


@dataclass
class ParsedExportFilters:
    period_start: date
    period_end: date
    review_results: list[ReviewResult]
    labels: list[int]
    exclude_labels: list[int]
    payment_methods: list[PaymentMethod]
    open_access_types: list[OpenAccessType]
    publication_states: list[str]
    invoice_status: str | None


def _parse_filter_dict(
    filters: dict[str, str],
) -> ParsedExportFilters:
    period_start = datetime.strptime(
        filters["period_start"],
        "%Y-%m-%d",
    ).date()

    period_end = datetime.strptime(
        filters["period_end"],
        "%Y-%m-%d",
    ).date()

    processing_status = [s for s in filters.get("processing_status", "").split(",") if s]

    review_results = [ReviewResult(rr) for rr in processing_status]

    payment_methods = [
        PaymentMethod(pm) for pm in filters.get("payment_methods", "").split(",") if pm
    ]

    open_access_types = [
        OpenAccessType(oat) for oat in filters.get("open_access_type", "").split(",") if oat
    ]

    publication_states = [ps for ps in filters.get("publication_states", "").split(",") if ps]

    labels = [int(_id) for _id in filters.get("labels", "").split(",") if _id]

    exclude_labels = [int(_id) for _id in filters.get("exclude_labels", "").split(",") if _id]

    payment_status = [ps for ps in filters.get("payment_status", "").split(",") if ps]

    invoice_status = payment_status[0] if payment_status else None

    return ParsedExportFilters(
        period_start=period_start,
        period_end=period_end,
        review_results=review_results,
        labels=labels,
        exclude_labels=exclude_labels,
        payment_methods=payment_methods,
        open_access_types=open_access_types,
        publication_states=publication_states,
        invoice_status=invoice_status,
    )


def _generate_csv_for_export(
    export: FundingRequestCSVExport,
) -> str:

    return _generate_csv_from_filters(
        export.filters,
    )


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


def _build_export_filters(
    request: HttpRequest,
) -> dict[str, str]:

    filters = {
        "period_start": request.POST["period_start"],
        "period_end": request.POST["period_end"],
    }

    optional_fields = [
        "processing_status",
        "payment_methods",
        "open_access_type",
        "publication_states",
        "labels",
        "exclude_labels",
        "payment_status",
    ]

    for field in optional_fields:
        values = request.POST.getlist(field)

        if values:
            filters[field] = ",".join(values)

    return filters


def _get_export_form_context() -> dict[str, Any]:

    return {
        "processing_states": [rr.value for rr in ReviewResult],
        "payment_methods": [(pm.value, pm.value) for pm in PaymentMethod],
        "open_access_types": [oat.value for oat in OpenAccessType],
        "publication_states": (_publication_state_choices),
        "payment_status_choices": (_payment_status_choices),
        "labels": Label.objects.all(),
    }


def _generate_csv_from_filters(
    filters: dict[str, str],
) -> str:

    parsed_filters = _parse_filter_dict(
        filters,
    )

    return export_fundingrequests_to_csv(
        **asdict(parsed_filters),
    )
