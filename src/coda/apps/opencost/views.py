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
from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportPublication,
    OpenCostReportPublicationContract,
)
from coda.apps.opencost.report_service import (
    generate_report as generate_report_service,
)
from coda.apps.opencost.services.issues import collect_issues
from coda.apps.opencost.services.queries import transform_ready_reports
from coda.apps.opencost.xml_generation import generate_xml
from coda.apps.preferences.models import GlobalPreferences
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
    # Minimal prefetch - only data displayed on detail page
    # identifiers/links/secondary_identifiers are only for XML generation
    report = get_object_or_404(
        OpenCostReport.objects.prefetch_related(
            Prefetch(
                "publications",
                queryset=OpenCostReportPublication.objects.select_related(
                    "publication__fundingrequest",  # For request_id in invoice link
                ).prefetch_related(
                    Prefetch(
                        "linked_contracts",
                        queryset=OpenCostReportPublicationContract.objects.select_related(
                            "contract",  # For contract names in table
                        ),
                    ),
                    "invoices",  # For counting only
                ),
            ),
            Prefetch(
                "contracts",
                queryset=OpenCostReportContract.objects.select_related(
                    "contract",  # For contract.id in links
                ).prefetch_related(
                    "invoices",  # For counting only
                ),
            ),
        ),
        pk=report_id,
    )

    # Convert to lists to force evaluation
    publications_list = list(report.publications.all())
    contracts_list = list(report.contracts.all())

    # Compute counts from already-prefetched data (no additional queries)
    # Access the prefetch cache directly by converting to list first
    for pub in publications_list:
        # Force evaluation of prefetch cache into a list to count
        linked_contracts_list = list(pub.linked_contracts.all())
        invoices_list = list(pub.invoices.all())
        setattr(pub, "linked_contracts_count", len(linked_contracts_list))
        setattr(pub, "invoices_count", len(invoices_list))

    for contract in contracts_list:
        contract_invoices_list = list(contract.invoices.all())
        setattr(contract, "invoices_count", len(contract_invoices_list))

    applied_filters = build_applied_filters(report.filters)
    redo_url = create_redo_url(report.filters, "opencost:generate")

    context = {
        "report": report,
        "publications": publications_list,
        "publications_count": len(publications_list),
        "contracts": contracts_list,
        "contracts_count": len(contracts_list),
        "applied_filters": applied_filters,
        "redo_url": redo_url,
    }

    return render(request, "opencost/report_detail.html", context)


@require_GET
@non_atomic_requests  # read-only, ~0.1 s, no txn held
def report_issues(request: HttpRequest, report_id: int) -> HttpResponse:
    if not request.user.is_authenticated:
        raise PermissionDenied  # 403: a fragment target cannot use a login page
    report = get_object_or_404(transform_ready_reports(), pk=report_id)
    issues = collect_issues(report)
    return render(
        request,
        "opencost/partials/report_issues.html",
        {
            "report": report,
            "failed": issues is None,
            "errors": [w for w in issues or () if w.level == "error"],
            "warnings_only": [w for w in issues or () if w.level == "warning"],
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


def _build_issue_message(report: OpenCostReport, detail_url: str) -> str:
    issue_counts = report.get_issue_counts()
    issue_parts = []

    if issue_counts["errors"] > 0:
        error_text = "error" if issue_counts["errors"] == 1 else "errors"
        issue_parts.append(f"{issue_counts['errors']} {error_text}")

    if issue_counts["warnings"] > 0:
        warning_text = "warning" if issue_counts["warnings"] == 1 else "warnings"
        issue_parts.append(f"{issue_counts['warnings']} {warning_text}")

    issue_text = " and ".join(issue_parts)

    return mark_safe(
        f"Report '{escape(report.title)}' generated with {report.publications.count()} publications "
        f"and {report.contracts.count()} contracts, but has {issue_text}. "
        f"<a href='{detail_url}'>Review what the XML leaves out</a>"
    )


def _build_success_message(report: OpenCostReport) -> str:
    return (
        f"Report '{report.title}' generated successfully with {report.publications.count()} "
        f"publications and {report.contracts.count()} contracts."
    )


def _exclusion_message(excluded: list[ValidationWarning]) -> str:
    """Summarise what the transformer had to leave out of the generated XML."""
    count = f"{len(excluded)} record" if len(excluded) == 1 else f"{len(excluded)} records"
    details = "; ".join(f"{warning.entity_name}: {warning.message}" for warning in excluded[:5])

    hidden = len(excluded) - 5
    if hidden > 0:
        details += f" (and {hidden} more)"

    return f"The openCost XML leaves out {count}: {details}"


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

    prefs = GlobalPreferences.objects.select_related("home_institution").first()
    if prefs is None or prefs.home_institution_id is None:
        # without a home institution no snapshot carries institution data, every record is
        # excluded, and the resulting XML would be empty — so do not create the report
        messages.error(
            request,
            "No home institution is set — the report was not generated, because none of its "
            "records could be exported to openCost XML. Set the home institution in "
            "preferences and generate again.",
        )
        return redirect("opencost:generate")

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
    report = get_object_or_404(transform_ready_reports(), pk=report_id)

    try:
        # Convert prefetched querysets to lists for transformer functions
        publications_list = list(report.publications.all())
        contracts_list = list(report.contracts.all())

        issues: list[ValidationWarning] = []
        xml_string = generate_xml(report, publications_list, contracts_list, issues)

        if not xml_string:
            errors = [w for w in issues if w.level == "error"]
            messages.warning(request, _no_data_message(errors))
            return redirect(OPENCOST_LIST_URL)

        response = HttpResponse(xml_string, content_type="application/xml")

        filename = f"{report.title}_{report.id}_{report.generated_at.strftime('%Y%m%d')}.xml"

        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        errors = [w for w in issues if w.level == "error"]
        if errors:
            messages.warning(request, _exclusion_message(errors))

        return response

    except Exception as e:
        messages.error(request, f"Error generating XML: {str(e)}")
        return redirect(OPENCOST_LIST_URL)


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
