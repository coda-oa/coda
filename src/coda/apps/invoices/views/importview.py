import pydantic
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.formbase import JsonUploadForm
from coda.contexts.finance.services.invoice_import import import_invoices, InvoiceImportReport


@login_required
@require_http_methods(["GET", "POST"])
@breadcrumb("Import Invoices", parent_url_name="invoices:list")
def import_invoices_view(request: HttpRequest) -> HttpResponse:
    import_errors = []
    form = get_form(request)
    if request.method != "POST" or not form.is_valid():
        return render_importview(request, form)

    import_file = form.cleaned_data["import_file"]
    try:
        report = import_invoices(import_file)
        import_errors = _handle_import_report(request, report)
    except pydantic.ValidationError as e:
        import_errors = [f"{error['loc']}: {error['msg']}" for error in e.errors()]

    return render_importview(request, form, import_errors=import_errors)


def _handle_import_report(request: HttpRequest, report: InvoiceImportReport) -> list[str]:
    if report.valid_invoices > 0:
        messages.success(request, f"Successfully imported {report.valid_invoices} invoice(s).")

    if report.invalid_invoices > 0:
        messages.warning(
            request,
            f"{report.invalid_invoices} invoice(s) failed to import. See details below.",
        )

    formatted_errors = []
    for error in report.errors:
        invoice_number, reasons = error.unpack()
        formatted_errors.append(f"{invoice_number}: {'; '.join(reasons)}")

    return formatted_errors


def get_form(request: HttpRequest) -> JsonUploadForm:
    if request.method == "POST":
        return JsonUploadForm(request.POST, request.FILES)
    return JsonUploadForm()


def render_importview(
    request: HttpRequest, form: JsonUploadForm, import_errors: list[str] | None = None
) -> HttpResponse:
    return render(
        request,
        "invoices/invoice_import.html",
        {"form": form, "import_errors": import_errors or []},
    )
