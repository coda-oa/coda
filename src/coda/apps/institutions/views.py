from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from coda.apps.institutions import repository, services
from coda.apps.institutions.models import Institution
from coda.apps.views import EntityListView


class InstitutionListView(LoginRequiredMixin, EntityListView[Institution]):
    entity_name = "Institution"
    entity_filter_template = "institutions/institution_filter.html"
    entity_list_item_template = "institutions/institution_list_item.html"

    def get_entities(self, request: HttpRequest) -> list[Institution]:
        return list(repository.search(name=request.GET.get("query")))


institution_list_view = InstitutionListView.as_view()


@login_required
def toggle_selectable(request: HttpRequest, pk: int) -> HttpResponse:
    institution = Institution.objects.get(pk=pk)
    institution.virtual = not institution.virtual
    institution.save()
    return HttpResponse()


@login_required
def import_view(request: HttpRequest) -> HttpResponse:
    return render(request, "institutions/institution_import.html")


@login_required
@require_POST
def import_from_file(request: HttpRequest) -> HttpResponse:
    uploaded_file = request.FILES["institution-list"]

    if not isinstance(uploaded_file, UploadedFile):
        raise ValueError("No file uploaded")

    with uploaded_file.open() as file:
        services.import_from_file(BytesIO(file.read()))

    messages.success(request, "Institutions imported successfully")
    return redirect("institutions:list")
