import pydantic
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.formbase import JsonUploadForm
from coda.contexts.finance.services.invoice_import import import_invoices


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
        import_invoices(import_file)
        messages.success(request, "Invoices imported successfully.")
    except pydantic.ValidationError as e:
        import_errors = [f"{error['loc']}: {error['msg']}" for error in e.errors()]

    return render_importview(request, form, import_errors=import_errors)


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
