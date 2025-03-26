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
        importservice.import_fundingrequests(import_file.read())

    return render_import_form(request)


def render_import_form(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "generic_form_view.html",
        {"title": "Import Funding Requests", "form": FundingRequestImportForm()},
    )
