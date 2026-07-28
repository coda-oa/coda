from django.contrib import messages
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_GET, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.exports.models import ContractCSVExport
from coda.apps.exports.services.contract_csv.export_service import export_contract_to_csv
from coda.apps.exports.services.filter_display import (
    build_applied_filters_for_contract,
    build_filter_form_context,
    build_filters_from_request,
    parse_date_range,
    parse_funding_source,
    parse_invoice_payment_status,
)
from coda.apps.exports.views.base_csv_views import (
    create_csv_export,
    csv_delete_view,
    csv_detail_page,
    csv_download_view,
)
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.finance.invoice import PaymentStatus

CONTRACTS_CSV_CREATE_URL = "exports:contracts_csv_create"
CONTRACTS_CSV_LIST_URL = "exports:contracts_csv_list"

PREVIEW_COLUMNS = [
    "contract_name",
    "invoice_number",
    "position_amount",
    "funded_amount",
    "funding_source_name",
]


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
@breadcrumb("CSV Export Details", parent_url_name=CONTRACTS_CSV_LIST_URL)
def contract_csv_detail_page(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_detail_page(
        request,
        pk,
        model=ContractCSVExport,
        template_name="export/contract_csv_detail.html",
        preview_columns=PREVIEW_COLUMNS,
        applied_filters_builder=build_applied_filters_for_contract,
        create_url_name="exports:contracts_csv_create",
    )


@login_required
@breadcrumb("Generate New CSV Export", parent_url_name=CONTRACTS_CSV_LIST_URL)
def contract_csv_export_create_view(request: HttpRequest) -> HttpResponse:

    if request.method == "GET":
        return _render_create_form(request)

    try:
        return create_csv_export(
            request,
            ContractCSVExport,
            build_filters=lambda req: build_filters_from_request(
                req, optional_fields=["payment_status", "funding_source"]
            ),
            generate_csv=_generate_csv_from_filters,
            detail_url_name="exports:contracts_csv_detail",
        )
    except ValueError as e:
        messages.error(request, str(e))
        return _render_create_form(request, status=400)


def _render_create_form(request: HttpRequest, status: int = 200) -> HttpResponse:
    context = build_filter_form_context()
    context["expand_advanced_search"] = bool(request.GET)
    context.update(
        {
            "page_title": "Generate Contract CSV Export",
            "form_action_url": reverse(CONTRACTS_CSV_CREATE_URL),
            "parameters_title": "Invoice Filter Parameters",
            "title_label": "Title",
            "title_placeholder": "Enter a title for the export",
            "cancel_url": reverse(CONTRACTS_CSV_LIST_URL),
            "submit_button_text": "Generate CSV Export",
            "show_filters": ["payment_status", "funding_source"],
            "payment_status_filter_template": "invoices/partials/payment_status_filter.html",
            "payment_statuses": [s.value for s in PaymentStatus],
        }
    )
    return render(request, "exports/generate_export_form.html", context=context, status=status)


@login_required
@require_POST
def contracts_csv_delete(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_delete_view(
        request, pk, model=ContractCSVExport, list_url_name=CONTRACTS_CSV_LIST_URL
    )


@login_required
@require_GET
def contract_download_csv(request: HttpRequest, pk: int) -> FileResponse:
    return csv_download_view(pk, model=ContractCSVExport)


def _parse_contract_filter_dict(filters: dict[str, str]) -> InvoiceSearchParams:
    try:
        date_range = parse_date_range(filters)
    except ValueError:
        raise ValueError("Invalid date format. Please enter dates in YYYY-MM-DD format.")

    return InvoiceSearchParams(
        date_range=date_range,
        payment_status=parse_invoice_payment_status(filters),
        funding_source=parse_funding_source(filters),
    )


def _generate_csv_from_filters(filters: dict[str, str]) -> str:
    params = _parse_contract_filter_dict(filters)
    return export_contract_to_csv(params)
