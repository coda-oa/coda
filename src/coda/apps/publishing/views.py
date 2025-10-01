from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from coda.apps.breadcrumbs.decorators import breadcrumb

@breadcrumb("Journals & Publishers")
def publishing_home(request: HttpRequest) -> HttpResponse:
    return render(request, "publishing/home.html")
