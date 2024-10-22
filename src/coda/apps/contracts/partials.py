from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


@login_required
def search_publisher(request: HttpRequest) -> HttpResponse:
    if search := request.GET.get("search-publisher"):
        publishers = Publisher.objects.filter(name__icontains=search)
    else:
        publishers = Publisher.objects.none()

    return render(
        request, "contracts/contract_search_publisher.html", {"search_results": publishers}
    )


@login_required
def search_journal(request: HttpRequest) -> HttpResponse:
    journals = []
    if search := request.GET.get("search-journal"):
        journals = [
            {"name": j.title, "id": j.id} for j in Journal.objects.filter(title__icontains=search)
        ]

    return render(request, "contracts/contract_search_publisher.html", {"search_results": journals})
