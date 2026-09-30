from collections.abc import Sequence
from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.db.transaction import non_atomic_requests
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainQuerySet
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
from coda.apps.opencost.detail_rows import build_detail_rows
from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportPublication,
)
from coda.apps.opencost.report_service import (
    generate_report as generate_report_service,
)
from coda.apps.opencost.report_service import (
    regenerate_report as regenerate_report_service,
)
from coda.apps.views import SimpleSearchEntityListView
from coda.contexts.exports.dto.filters import ExportFiltersDto

OPENCOST_LIST_URL = "opencost:list"


@breadcrumb("openCost Reports", parent_url_name="exports:export_home")
class ReportListView(LoginRequiredMixin, SimpleSearchEntityListView[OpenCostReport]):
    model = OpenCostReport
    paginate_by = 20
    entity_name = "openCost Reports"
    entity_list_item_template = "opencost/report_list_item.html"
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"
    search_fields = ["title"]
    search_placeholder = "Search by report title"
    entity_create_url = "opencost:generate"
    ordering = ["-generated_at"]

    def get_entities(self, request: HttpRequest) -> Sequence[OpenCostReport]:
        search_term = request.GET.get("query", "").strip()
        queryset = self.model.objects.all()

        if search_term:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search_term})
            queryset = queryset.filter(query)

        # The badges read the issues JSON row-locally; the XML artifact is only ever needed
        # one report at a time, so the list never carries it.
        queryset = queryset.defer("xml_content")

        # Annotate with counts to avoid N+1 queries in the template
        queryset = queryset.annotate(
            publications_count=Count("publications", distinct=True),
            contracts_count=Count("contracts", distinct=True),
        )

        queryset = queryset.order_by(*self.ordering)
        return DomainQuerySet(queryset, lambda x: x)


report_list_view = ReportListView.as_view()


@login_required
@require_GET
@breadcrumb("Report Details", parent_url_name=OPENCOST_LIST_URL)
def report_detail(request: HttpRequest, report_id: int) -> HttpResponse:
    report = get_object_or_404(
        OpenCostReport.objects.prefetch_related(
            Prefetch(
                "publications",
                queryset=OpenCostReportPublication.objects.select_related(
                    "publication__fundingrequest",  # For request_id in invoice link
                ).prefetch_related("invoices"),  # For counting only
            ),
            Prefetch(
                "contracts",
                queryset=OpenCostReportContract.objects.select_related(
                    "contract",  # For contract.id in links
                ).prefetch_related("invoices"),  # For counting only
            ),
        ),
        pk=report_id,
    )

    rows = build_detail_rows(report)

    context = {
        "report": report,
        "publications": rows.publications,
        "contracts": rows.contracts,
        "applied_filters": build_applied_filters(report.filters),
        "redo_url": create_redo_url(report.filters, "opencost:generate"),
    }

    return render(request, "opencost/report_detail.html", context)


@require_GET
@non_atomic_requests  # read-only, one row, no txn held
def report_issues(request: HttpRequest, report_id: int) -> HttpResponse:
    if not request.user.is_authenticated:
        raise PermissionDenied  # 403: a fragment target cannot use a login page
    report = get_object_or_404(OpenCostReport, pk=report_id)
    issues = report.issues or []
    return render(
        request,
        "opencost/partials/report_issues.html",
        {
            "report": report,
            "errors": [w for w in issues if w.get("level") == "error"],
            "warnings_only": [w for w in issues if w.get("level") == "warning"],
        },
    )


@login_required
@require_GET
@breadcrumb("Generate New Report", parent_url_name=OPENCOST_LIST_URL)
def generate_report_form(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "exports/generate_export_form.html",
        _report_form_context(request, FundingRequestFilterForm()),
    )


def _issue_summary(report: OpenCostReport) -> str:
    """The report's stored issue counts as words, e.g. '2 errors and 1 warning'."""
    issue_counts = report.get_issue_counts()
    issue_parts = []

    if issue_counts["errors"] > 0:
        error_text = "error" if issue_counts["errors"] == 1 else "errors"
        issue_parts.append(f"{issue_counts['errors']} {error_text}")

    if issue_counts["warnings"] > 0:
        warning_text = "warning" if issue_counts["warnings"] == 1 else "warnings"
        issue_parts.append(f"{issue_counts['warnings']} {warning_text}")

    return " and ".join(issue_parts)


def _build_issue_message(report: OpenCostReport, detail_url: str) -> str:
    return mark_safe(
        f"Report '{escape(report.title)}' generated with {report.publications.count()} publications "
        f"and {report.contracts.count()} contracts, but has {_issue_summary(report)}. "
        f"<a href='{detail_url}'>Review what the XML leaves out</a>"
    )


def _build_success_message(report: OpenCostReport) -> str:
    return (
        f"Report '{report.title}' generated successfully with {report.publications.count()} "
        f"publications and {report.contracts.count()} contracts."
    )


def _build_regeneration_message(report: OpenCostReport, detail_url: str) -> str:
    return mark_safe(
        f"Report '{escape(report.title)}' regenerated with {report.publications.count()} "
        f"publications and {report.contracts.count()} contracts, but has {_issue_summary(report)}. "
        f"<a href='{detail_url}'>Review what the XML leaves out</a>"
    )


def _build_regeneration_success_message(report: OpenCostReport) -> str:
    return (
        f"Report '{report.title}' regenerated successfully with {report.publications.count()} "
        f"publications and {report.contracts.count()} contracts."
    )


def _no_data_message(excluded: list[ValidationWarning]) -> str:
    if not excluded:
        return "No data to export — the report has no publications or contracts to transform."

    details = "; ".join(f"{warning.entity_name}: {warning.message}" for warning in excluded[:5])

    hidden = len(excluded) - 5
    if hidden > 0:
        details += f" (and {hidden} more)"

    return (
        "No file was downloaded: nothing in this report could be transformed into openCost XML. "
        f"Reasons: {details}"
    )


@login_required
@require_POST
def generate_report(request: HttpRequest) -> HttpResponse:
    form = FundingRequestFilterForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "exports/generate_export_form.html",
            _report_form_context(
                request,
                form,
                form_errors=form_error_lines(form),
                current_filters=current_filters_from_post(request.POST),
            ),
        )

    cleaned = cast(FilterCleanedData, form.cleaned_data)
    title = cleaned["title"].strip() or "OpenCost Report"
    dto = ExportFiltersDto.from_form_data(cleaned)

    try:
        report = generate_report_service(
            title=title,
            filters=dto.to_storage(),
        )
    except Exception as e:
        messages.error(request, f"Error generating report: {str(e)}")
        return redirect("opencost:generate")

    if report.has_issues():
        detail_url = reverse("opencost:detail", args=[report.id])
        message = _build_issue_message(report, detail_url)
        messages.warning(request, message)
    else:
        message = _build_success_message(report)
        messages.success(request, message)

    return redirect(OPENCOST_LIST_URL)


def _report_form_context(
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
            "page_title": "Generate New openCost Report",
            "form_action_url": reverse("opencost:generate_submit"),
            "parameters_title": "Report Parameters",
            "title_label": "Report Title",
            "title_placeholder": "Enter a title for the report",
            "cancel_url": reverse(OPENCOST_LIST_URL),
            "submit_button_text": "Generate Report",
            "include_payment_status": False,
            "include_decimal_separator": False,
        }
    )
    if form_errors is not None:
        context["form_errors"] = form_errors
    return context


@login_required
@require_GET
def download_xml(request: HttpRequest, report_id: int) -> HttpResponse:
    report = get_object_or_404(OpenCostReport, pk=report_id)

    if not report.xml_content:
        # Nothing was exportable; the stored issue log says why, in the same message the
        # download-time transform used to produce.
        errors = [
            ValidationWarning(**issue)
            for issue in report.issues or []
            if issue.get("level") == "error"
        ]
        messages.warning(request, _no_data_message(errors))
        return redirect(OPENCOST_LIST_URL)

    response = HttpResponse(report.xml_content, content_type="application/xml")

    filename = f"{report.title}_{report.id}_{report.generated_at.strftime('%Y%m%d')}.xml"

    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


@login_required
@require_POST
def regenerate_report(request: HttpRequest, report_id: int) -> HttpResponse:
    """Rebuild the report's document over its stored membership, from current CODA data.

    Answered like the delete view: the button posts through htmx, and the HX-Redirect sends
    the browser on a full navigation to the detail page - the one way both the flash message
    and the regenerated state it describes reach the user's eyes.
    """
    report = get_object_or_404(OpenCostReport, pk=report_id)
    detail_url = reverse("opencost:detail", args=[report.id])

    try:
        report = regenerate_report_service(report)
    except Exception as e:
        # Only the run itself is guarded: its failure is data the user can fix, and the
        # flash says so. A defect in building the flash is a bug, and bugs flash as 500s.
        messages.error(request, f"Error regenerating report: {str(e)}")
    else:
        if report.has_issues():
            messages.warning(request, _build_regeneration_message(report, detail_url))
        else:
            messages.success(request, _build_regeneration_success_message(report))

    response = HttpResponse(status=200)
    response["HX-Redirect"] = detail_url
    return response


@login_required
@require_POST
def delete_report(request: HttpRequest, report_id: int) -> HttpResponse:
    report = get_object_or_404(OpenCostReport, pk=report_id)
    report_title = report.title
    report.delete()
    messages.success(request, f"Report '{report_title}' deleted successfully.")

    response = HttpResponse(status=200)
    response["HX-Redirect"] = reverse(OPENCOST_LIST_URL)
    return response
