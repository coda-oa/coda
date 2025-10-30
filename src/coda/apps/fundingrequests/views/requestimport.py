from typing import BinaryIO, cast

import pydantic
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.formbase import JsonUploadForm
from coda.apps.fundingrequests.services import importservice
from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.fundingrequests.services.importservice._import import FundingRequestImportReport


@login_required
@breadcrumb("Import Funding Requests", parent_url_name="fundingrequests:list")
def import_fundingrequests(request: HttpRequest) -> HttpResponse:
    import_errors = []
    if request.method != "POST":
        return render_import_form(request)

    form = JsonUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Invalid uploaded file")
        return render_import_form(request)

    import_file: UploadedFile = form.cleaned_data["import_file"]

    try:
        report = importservice.import_fundingrequests(cast(BinaryIO, import_file))
        import_errors = _handle_import_errors(request, report)
    except pydantic.ValidationError as e:
        import_errors = [f"{error['loc']}: {error['msg']}" for error in e.errors()]
    except Exception as e:
        messages.error(request, f"Import failed: {str(e)}")

    return render_import_form(request, import_errors=import_errors)


def _handle_import_errors(request: HttpRequest, report: FundingRequestImportReport) -> list[str]:
    import_errors: list[str] = []
    if report.valid_requests > 0:
        messages.success(
            request, f"Successfully imported {report.valid_requests} funding request(s)."
        )
    if report.invalid_requests > 0:
        messages.warning(
            request,
            f"{report.invalid_requests} request(s) failed to import. See details below.",
        )
        for request_key, errors in report.errors.items():
            for error in errors:
                import_errors.append(f"{request_key}: {error}")

    return import_errors


def render_import_form(
    request: HttpRequest, *, import_errors: list[str] | None = None
) -> HttpResponse:
    return render(
        request,
        "fundingrequests/fundingrequest_import.html",
        {"form": JsonUploadForm(), "import_errors": import_errors},
    )
