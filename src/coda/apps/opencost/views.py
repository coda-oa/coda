from typing import cast

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Count
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Q
from collections.abc import Sequence

from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportInvoice,
    OpenCostReportInvoicePosition,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportPublication,
    OpenCostReportContract,
    OpenCostReportPublicationContract,
)
from coda.apps.contracts.models import ContractLink
from coda.apps.opencost.report_service import (
    generate_report as generate_report_service,
)
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
from coda.contexts.exports.dto.filters import ExportFiltersDto
from coda.apps.opencost.validation import validate_report
from coda.apps.opencost.xml_generation import generate_xml
from coda.apps.views import SimpleSearchEntityListView
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.breadcrumbs.decorators import breadcrumb

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

    # Pass pre-loaded data to validation to avoid duplicate queries
    warnings = validate_report(report, contracts=contracts_list, publications=publications_list)
    errors = [w for w in warnings if w.level == "error"]
    warnings_only = [w for w in warnings if w.level == "warning"]
    applied_filters = build_applied_filters(report.filters)
    redo_url = create_redo_url(report.filters, "opencost:generate")

    context = {
        "report": report,
        "publications": publications_list,
        "publications_count": len(publications_list),
        "contracts": contracts_list,
        "contracts_count": len(contracts_list),
        "warnings": warnings,
        "errors": errors,
        "warnings_only": warnings_only,
        "has_issues": len(warnings) > 0,
        "applied_filters": applied_filters,
        "redo_url": redo_url,
    }

    return render(request, "opencost/report_detail.html", context)


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
        f"Report '{report.title}' generated with {report.publications.count()} publications "
        f"and {report.contracts.count()} contracts, but has {issue_text}. "
        f"<a href='{detail_url}'>View details</a>"
    )


def _build_success_message(report: OpenCostReport) -> str:
    return (
        f"Report '{report.title}' generated successfully with {report.publications.count()} "
        f"publications and {report.contracts.count()} contracts."
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
    # Prefetch all related data upfront to avoid N+1 queries during XML generation
    report = get_object_or_404(
        OpenCostReport.objects.prefetch_related(
            Prefetch(
                "publications",
                queryset=OpenCostReportPublication.objects.prefetch_related(
                    "institution_identifiers",
                    "links",
                    Prefetch(
                        "linked_contracts",
                        queryset=OpenCostReportPublicationContract.objects.select_related(
                            "contract",
                        ).prefetch_related(
                            Prefetch(
                                "contract__links",
                                queryset=ContractLink.objects.select_related("type"),
                            ),
                        ),
                    ),
                    Prefetch(
                        "invoices",
                        queryset=OpenCostReportInvoice.objects.prefetch_related(
                            Prefetch(
                                "positions",
                                queryset=OpenCostReportInvoicePosition.objects.all(),
                            ),
                        ),
                    ),
                ),
            ),
            Prefetch(
                "contracts",
                queryset=OpenCostReportContract.objects.select_related(
                    "report",
                ).prefetch_related(
                    "institution_identifiers",
                    "secondary_identifiers",
                    Prefetch(
                        "invoices",
                        queryset=OpenCostReportContractInvoice.objects.prefetch_related(
                            Prefetch(
                                "positions",
                                queryset=OpenCostReportContractInvoicePosition.objects.all(),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        pk=report_id,
    )

    try:
        # Convert prefetched querysets to lists for transformer functions
        publications_list = list(report.publications.all())
        contracts_list = list(report.contracts.all())

        xml_string = generate_xml(report, publications_list, contracts_list)

        response = HttpResponse(xml_string, content_type="application/xml")

        filename = f"{report.title}_{report.id}_{report.generated_at.strftime('%Y%m%d')}.xml"

        response["Content-Disposition"] = f'attachment; filename="{filename}"'

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
