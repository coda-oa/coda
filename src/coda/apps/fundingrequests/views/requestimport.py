from typing import BinaryIO, cast

import pydantic
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from django.forms import widgets
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests.services import importservice


class FundingRequestImportForm(forms.Form):
    import_file = forms.FileField(widget=widgets.FileInput(attrs={"accept": ".json"}))


@login_required
def import_fundingrequests(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = FundingRequestImportForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Invalid uploaded file")
            return render_import_form(request)

        import_file: UploadedFile = form.cleaned_data["import_file"]
        import_errors = []
        try:
            importservice.import_fundingrequests(cast(BinaryIO, import_file))
        except pydantic.ValidationError as e:
            import_errors = [f"{error['loc']}: {error['msg']}" for error in e.errors()]

    return render_import_form(request, import_errors=import_errors)


def render_import_form(
    request: HttpRequest, *, import_errors: list[str] | None = None
) -> HttpResponse:
    return render(
        request,
        "fundingrequests/fundingrequest_import.html",
        {"form": FundingRequestImportForm(), "import_errors": import_errors},
    )
