from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_GET, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.exports.services.filter_display import (
    build_applied_filters,
    build_filter_form_context,
    build_filters_from_request,
    parse_common_filter_fields,
    parse_current_filters_to_context,
)
from coda.apps.exports.views.base_csv_views import (
    create_csv_export,
    csv_delete_view,
    csv_detail_page,
    csv_download_view,
)
from coda.apps.views import SimpleSearchEntityListView

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
@breadcrumb("CSV Export Details", parent_url_name=FUNDINGREQUESTS_CSV_LIST_URL)
def fundingrequest_csv_detail_page(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_detail_page(
        request,
        pk,
        model=FundingRequestCSVExport,
        template_name="export/fundingrequest_csv_detail.html",
        preview_columns=PREVIEW_COLUMNS,
        applied_filters_builder=build_applied_filters,
        create_url_name="exports:fundingrequests_csv_create",
    )


@login_required
@breadcrumb("Generate New CSV Export", parent_url_name=FUNDINGREQUESTS_CSV_LIST_URL)
def fundingrequest_csv_export_create_view(request: HttpRequest) -> HttpResponse:

    if request.method == "GET":
        context = build_filter_form_context()
        context["expand_advanced_search"] = bool(request.GET)
        context["current_filters"] = parse_current_filters_to_context(request)
        context.update(
            {
                "page_title": "Generate New CSV Export",
                "form_action_url": reverse(FUNDINGREQUESTS_CSV_CREATE_URL),
                "parameters_title": "Export Parameters",
                "title_label": "Title",
                "title_placeholder": "Enter a title for the export",
                "cancel_url": reverse(FUNDINGREQUESTS_CSV_LIST_URL),
                "submit_button_text": "Generate CSV Export",
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

        return render(request, "exports/generate_export_form.html", context=context)

    return create_csv_export(
        request,
        FundingRequestCSVExport,
        build_filters=build_filters_from_request,
        generate_csv=_generate_csv_from_filters,
        detail_url_name="exports:fundingrequests_csv_detail",
    )


@login_required
@require_POST
def fundingrequest_csv_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    return csv_delete_view(
        request, pk, model=FundingRequestCSVExport, list_url_name=FUNDINGREQUESTS_CSV_LIST_URL
    )


@login_required
@require_GET
def fundingrequest_download_csv(request: HttpRequest, pk: int) -> FileResponse:
    return csv_download_view(pk, model=FundingRequestCSVExport)


def _generate_csv_from_filters(filters: dict[str, str]) -> str:
    params = parse_common_filter_fields(filters)
    return export_fundingrequests_to_csv(params)
