from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.breadcrumbs.decorators import breadcrumb


@login_required
@breadcrumb("Export")
def export_home(request: HttpRequest) -> HttpResponse:
    return render(request, "export/export_home.html")
