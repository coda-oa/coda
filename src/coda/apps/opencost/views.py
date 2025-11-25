from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin

from coda.apps.views import SimpleSearchEntityListView

from .models import OpenCostReport
from .report_service import generate_report as generate_report_service
from .xml_generation import generate_xml
from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Export")
class ReportListView(LoginRequiredMixin, SimpleSearchEntityListView[OpenCostReport]):
    model = OpenCostReport
    paginate_by = 20
    entity_name = "Export"
    entity_list_item_template = "opencost/report_list_item.html"
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"
    search_fields = ["title"]
    search_placeholder = "Search by report title"
    entity_create_url = "opencost:generate"


report_list_view = ReportListView.as_view()


@login_required
@breadcrumb("Generate New Report", parent_url_name="opencost:list")
def generate_report(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        title = request.POST.get("title", "OpenCost Report")

        try:
            period_start_str = request.POST.get("period_start")
            period_end_str = request.POST.get("period_end")

            if not period_start_str or not period_end_str:
                messages.error(request, "Both start and end dates are required.")
                return redirect("opencost:generate")

            period_start = datetime.strptime(period_start_str, "%Y-%m-%d").date()
            period_end = datetime.strptime(period_end_str, "%Y-%m-%d").date()

            report = generate_report_service(
                title=title,
                period_start=period_start,
                period_end=period_end,
            )

            messages.success(
                request,
                f"Report '{report.title}' generated successfully with {report.publications.count()} publications.",
            )

            return redirect("opencost:list")

        except ValueError as e:
            messages.error(request, f"Invalid date format: {str(e)}")
            return redirect("opencost:generate")
        except Exception as e:
            messages.error(request, f"Error generating report: {str(e)}")
            return redirect("opencost:generate")

    return render(request, "opencost/generate_report.html")


@login_required
def download_xml(request: HttpRequest, report_id: int) -> HttpResponse:
    report = get_object_or_404(OpenCostReport, pk=report_id)

    try:
        xml_string = generate_xml(report)

        response = HttpResponse(xml_string, content_type="application/xml")

        filename = f"{report.title}_{report.id}_{report.generated_at.strftime('%Y%m%d')}.xml"

        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        messages.error(request, f"Error generating XML: {str(e)}")
        return redirect("opencost:list")
