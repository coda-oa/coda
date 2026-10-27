from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from coda.apps.breadcrumbs.decorators import breadcrumb


@login_required
@require_GET
@breadcrumb("Reporting")
def reporting_home(request: HttpRequest) -> HttpResponse:
    return render(request, "reporting/home.html")
