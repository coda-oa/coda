from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.publications.models import LinkType


@login_required
def add_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "fundingrequests/partials/linkrow.html",
        {"link_types": LinkType.objects.all()},
    )
