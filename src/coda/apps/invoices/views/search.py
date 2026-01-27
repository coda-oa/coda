from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from coda.apps.contracts.models import Contract
from coda.apps.invoices.views.position_parsers import maybe_request_context
from coda.apps.publications.models import Publication


@login_required
def search_publications(request: HttpRequest) -> HttpResponse:
    query = request.POST.get("q", "")
    if query:
        publications = Publication.objects.filter(
            Q(title__icontains=query) | Q(links__type__name="DOI", links__value__icontains=query)
        ).distinct()
    else:
        publications = Publication.objects.none()

    search_results = [search_result_for_publication(pub) for pub in publications]
    return render(request, "invoices/search_publications.html", {"publications": search_results})


def search_result_for_publication(publication: Publication) -> dict[str, Any]:
    return {
        "id": publication.id,
        "title": publication.title,
        "funding_request": maybe_request_context(publication).to_post_data(),
    }


@login_required
def search_contracts(request: HttpRequest) -> HttpResponse:
    query = request.POST.get("contract_query", "")
    if query:
        contracts = Contract.objects.filter(
            Q(name__icontains=query) | Q(links__type__name="ESAC", links__value__icontains=query)
        ).distinct()
    else:
        contracts = Contract.objects.none()

    search_results = [search_results_for_contract(contract) for contract in contracts]
    return render(request, "invoices/search_contracts.html", {"contracts": search_results})


def search_results_for_contract(contract: Contract) -> dict[str, Any]:
    return {
        "id": contract.id,
        "name": contract.name,
        "url": reverse("contracts:detail", kwargs={"pk": contract.id}),
    }
