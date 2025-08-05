from typing import BinaryIO, cast

import pydantic
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.formbase import JsonUploadForm
from coda.apps.fundingrequests.services import importservice


@login_required
def import_fundingrequests(request: HttpRequest) -> HttpResponse:
    import_errors = []
    if request.method == "POST":
        form = JsonUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Invalid uploaded file")
            return render_import_form(request)

        import_file: UploadedFile = form.cleaned_data["import_file"]
        try:
            importservice.import_fundingrequests(cast(BinaryIO, import_file))
            messages.success(request, "Funding requests imported successfully.")
        except pydantic.ValidationError as e:
            import_errors = [f"{error['loc']}: {error['msg']}" for error in e.errors()]

    return render_import_form(request, import_errors=import_errors)


def render_import_form(
    request: HttpRequest, *, import_errors: list[str] | None = None
) -> HttpResponse:
    return render(
        request,
        "fundingrequests/fundingrequest_import.html",
        {"form": JsonUploadForm(), "import_errors": import_errors},
    )
