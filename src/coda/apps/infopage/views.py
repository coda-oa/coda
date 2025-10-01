from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from coda.apps.breadcrumbs.decorators import breadcrumb


@require_GET
@breadcrumb("Information on CODA")  
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "infopage/info_page.html")
