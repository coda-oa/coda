from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import (
    require_GET,
    require_POST,
    require_http_methods,
)

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.exports.models import ContractCSVExport
from coda.apps.exports.services.contract_csv.export_service import export_contract_to_csv
from coda.apps.exports.services.filter_display import (
    build_applied_filters_for_contract,
    build_filter_form_context,
    create_contract_redo_url,
    parse_current_filters_to_context,
)
from coda.apps.exports.services.filter_form import (
    ContractExportConfigForm,
    ContractExportFilters,
    FormFieldErrors,
    current_filters_from_post,
    form_error_lines,
)
from coda.apps.exports.views.base_csv_views import (
    csv_delete_view,
    csv_detail_page,
    csv_download_view,
    csv_regen_view,
    save_export_csv_file,
)
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.date import DateRange
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
        redo_url_builder=create_contract_redo_url,
        regen_url_name="exports:contracts_csv_regen",
    )


@login_required
@require_POST
def contract_csv_regen_view(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_regen_view(
        pk,
        model=ContractCSVExport,
        generate_csv=_wrapped_generate_csv_from_filters,
        detail_url_name="exports:contracts_csv_detail",
    )


def _wrapped_generate_csv_from_filters(json: dict[str, str]) -> str:
    # TODO: this is a workaround due to the newly introduced pydantic based filters.
    # unify filter approaches later
    filters = ContractExportFilters.model_validate(json)
    return _generate_csv_from_filters(filters)


@login_required
@require_http_methods(["GET", "POST"])
@breadcrumb("Generate New CSV Export", parent_url_name=CONTRACTS_CSV_LIST_URL)
def contract_csv_export_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ContractExportConfigForm(request.POST)
        if not form.is_valid():
            return _render_create_form(
                request, form, form_errors=form_error_lines(form), status=400
            )

        filters = form.get_filters()
        csv_content = _generate_csv_from_filters(filters)

        export = ContractCSVExport.objects.create(
            name=form.get_title(),
            filters=filters.model_dump(mode="json"),
            record_count=0,
        )
        save_export_csv_file(export, csv_content)

        return redirect("exports:contracts_csv_detail", pk=export.pk)

    return _render_create_form(request)


def _render_create_form(
    request: HttpRequest,
    form: ContractExportConfigForm | None = None,
    form_errors: list[FormFieldErrors] | None = None,
    status: int = 200,
) -> HttpResponse:
    if form is None:
        form = ContractExportConfigForm()
    context = build_filter_form_context()
    context["form"] = form
    context["expand_advanced_search"] = bool(request.GET) or form_errors is not None
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
            "include_decimal_separator": True,
            "payment_status_filter_template": "invoices/partials/payment_status_filter.html",
            "payment_statuses": [s.value for s in PaymentStatus],
        }
    )
    context["current_filters"] = (
        current_filters_from_post(request.POST)
        if request.method == "POST"
        else parse_current_filters_to_context(request)
    )

    if form_errors is not None:
        context["form_errors"] = form_errors

    return render(request, "exports/generate_export_form.html", context=context, status=status)


@login_required
@require_POST
def contract_csv_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_delete_view(
        request, pk, model=ContractCSVExport, list_url_name=CONTRACTS_CSV_LIST_URL
    )


@login_required
@require_GET
def contract_download_csv(request: HttpRequest, pk: int) -> FileResponse | HttpResponse:
    return csv_download_view(pk, model=ContractCSVExport)


def _generate_csv_from_filters(filters: ContractExportFilters) -> str:
    date_range = DateRange.create(start=filters.period_start, end=filters.period_end)
    params = InvoiceSearchParams(
        date_range=date_range,
        payment_status=filters.payment_status,
        funding_source=filters.funding_source,
        decimal_separator=filters.decimal_separator,
    )
    return export_contract_to_csv(params)
