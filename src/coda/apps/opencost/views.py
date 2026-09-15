import logging
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple, cast

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

import opencost
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
)
from coda.apps.opencost.report_service import (
    generate_report as generate_report_service,
)
from coda.apps.opencost.report_service import (
    regenerate_report as regenerate_report_service,
)
from coda.apps.views import SimpleSearchEntityListView
from coda.contexts.exports.dto.filters import ExportFiltersDto
from opencost import Data

logger = logging.getLogger(__name__)

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


class DetailPublication(NamedTuple):
    """One publication row of the detail table: seed columns joined onto the stored document."""

    seed: OpenCostReportPublication
    fundingrequest_id: int | None
    title: str  # the seed column: a DOI-bearing publication names no title in the XML
    publisher: str  # the seed column, same reason
    doi: str
    publication_type: str
    contract_esac: str
    external_costsplitting: bool | None
    invoice_count: int
    status: str  # "clean" | "degraded" | "excluded"
    reasons: str  # error-level issue messages naming this entity


class DetailContract(NamedTuple):
    """One contract row of the detail table, joined the same way."""

    seed: OpenCostReportContract
    contract_id: int
    name: str
    esac: str
    institution_name: str
    participation_from: str
    participation_to: str
    invoice_count: int
    status: str
    reasons: str


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

    # The stored document is the row data's source; an all-excluded report legitimately has
    # none, in which case the seed rows and the issue log are rendered without it.
    document = _stored_document(report)
    error_issues = _error_issues_by_entity(report)

    publications = [
        _publication_detail(
            row, document, _issues_for(error_issues, "publication", row.publication_id)
        )
        for row in report.publications.all()
    ]
    contracts = [
        _contract_detail(row, document, _issues_for(error_issues, "contract", row.contract_id))
        for row in report.contracts.all()
    ]

    applied_filters = build_applied_filters(report.filters)
    redo_url = create_redo_url(report.filters, "opencost:generate")

    context = {
        "report": report,
        "publications": publications,
        "publications_count": len(publications),
        "contracts": contracts,
        "contracts_count": len(contracts),
        "applied_filters": applied_filters,
        "redo_url": redo_url,
    }

    return render(request, "opencost/report_detail.html", context)


def _stored_document(report: OpenCostReport) -> Data | None:
    """The stored XML as models - None when there is none or it no longer parses.

    Empty content is not a failure: a report whose every item was excluded has no document,
    and from_xml would raise on the empty string. A document that cannot be parsed degrades
    every exported row to its issue entry instead of failing the page.
    """
    if not report.xml_content:
        return None
    try:
        return opencost.from_xml(report.xml_content)
    except Exception:
        logger.exception("Stored openCost XML of report %s could not be parsed", report.pk)
        return None


def _error_issues_by_entity(report: OpenCostReport) -> dict[int, list[dict[str, Any]]]:
    """The stored issue log grouped by the entity each error names, for the detail-row join.

    Grouping is on ``entity_id`` alone; whether an issue belongs to a given row is decided
    per row by ``_issues_for``, since ids collide across CODA tables. ``global`` issues -
    exclusions caused by the institution settings - keep the identity of the item they
    were reported on, so they join onto that item's row too.
    """
    grouped: dict[int, list[dict[str, Any]]] = {}
    for issue in report.issues or []:
        entity_id = issue.get("entity_id")
        if issue.get("level") == "error" and entity_id is not None:
            grouped.setdefault(int(entity_id), []).append(issue)
    return grouped


def _issues_for(
    grouped: Mapping[int, list[dict[str, Any]]], entity_type: str, entity_id: int
) -> list[dict[str, Any]]:
    """The error issues naming one detail row.

    Entity ids are only unique per CODA table, so the stored entity type must match too:
    a publication and a contract can share an id, and one's exclusion reason must not
    decorate the other's row. Global institution exclusions are reported under the
    identity of the item they name - type "global", that item's own id - so they join
    onto that row as well.
    """
    return [
        issue
        for issue in grouped.get(entity_id, [])
        if issue.get("entity_type") in (entity_type, "global")
    ]


def _publication_detail(
    row: OpenCostReportPublication,
    document: Data | None,
    issues: list[dict[str, Any]],
) -> DetailPublication:
    """The row as the table shows it: from the XML entry the ordinal names, else from issues."""
    reasons = "; ".join(str(issue.get("message", "")) for issue in issues)
    element = _entry_at(document.publication if document else None, row)
    if element is None:
        # Excluded - or exported by the flags yet named no entry the document holds; either
        # way the row falls back to its issue log and the kept seed columns.
        return DetailPublication(
            seed=row,
            fundingrequest_id=_fundingrequest_id(row),
            title=row.title,
            publisher=row.publisher,
            doi="",
            publication_type="",
            contract_esac="",
            external_costsplitting=None,
            invoice_count=0,
            status="excluded",
            reasons=reasons,
        )

    part_of_contract = element.cost_data.part_of_contract
    return DetailPublication(
        seed=row,
        fundingrequest_id=_fundingrequest_id(row),
        title=row.title,
        publisher=row.publisher,
        doi=element.primary_identifier.doi or "",
        publication_type=element.publication_type.value if element.publication_type else "",
        contract_esac=(part_of_contract.primary_identifier.value if part_of_contract else ""),
        external_costsplitting=element.external_costsplitting,
        invoice_count=len(element.cost_data.invoice or []),
        status="degraded" if row.had_errors else "clean",
        reasons=reasons,
    )


def _contract_detail(
    row: OpenCostReportContract,
    document: Data | None,
    issues: list[dict[str, Any]],
) -> DetailContract:
    """The row as the table shows it: from the XML entry the ordinal names, else from issues."""
    reasons = "; ".join(str(issue.get("message", "")) for issue in issues)
    element = _entry_at(document.contract if document else None, row)
    if element is None:
        name = str(issues[0].get("entity_name") or "") if issues else ""
        return DetailContract(
            seed=row,
            contract_id=row.contract_id,
            name=name or row.contract_name,
            esac="",
            institution_name="",
            participation_from="",
            participation_to="",
            invoice_count=0,
            status="excluded",
            reasons=reasons,
        )

    names = element.institution.name if element.institution else None
    invoice_groups = element.cost_data.invoice_group
    return DetailContract(
        seed=row,
        contract_id=row.contract_id,
        name=element.contract_name,
        esac=element.primary_identifier.value,
        institution_name=names[0].value if names else "",
        participation_from=element.participation.from_ or "",
        participation_to=element.participation.to or "",
        invoice_count=len(invoice_groups[0].invoice or []) if invoice_groups else 0,
        status="degraded" if row.had_errors else "clean",
        reasons=reasons,
    )


def _entry_at[T](
    entries: Sequence[T] | None, row: OpenCostReportPublication | OpenCostReportContract
) -> T | None:
    """The document entry a seed row's ordinal names; None when it names none.

    Defensive by design: a regenerate racing between the report and the seed-row queries can
    leave an ordinal the freshly parsed document does not have. That row degrades to its
    issue entry; the page never fails over it.
    """
    if entries is None or not row.exported or row.xml_ordinal is None:
        return None
    if not 0 <= row.xml_ordinal < len(entries):
        return None
    return entries[row.xml_ordinal]


def _fundingrequest_id(row: OpenCostReportPublication) -> int | None:
    """The request the publication was filed under, when it was filed at all."""
    fundingrequest = getattr(row.publication, "fundingrequest", None)
    return None if fundingrequest is None else int(fundingrequest.id)


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
    """Rebuild the report's document over its stored membership, from current CODA data."""
    report = get_object_or_404(OpenCostReport, pk=report_id)
    detail_url = reverse("opencost:detail", args=[report.id])

    try:
        report = regenerate_report_service(report)
    except Exception as e:
        messages.error(request, f"Error regenerating report: {str(e)}")
        return redirect(detail_url)

    if report.has_issues():
        messages.warning(request, _build_regeneration_message(report, detail_url))
    else:
        messages.success(request, _build_regeneration_success_message(report))

    return redirect(detail_url)


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
