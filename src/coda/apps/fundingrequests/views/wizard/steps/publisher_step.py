from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from coda.apps.dto import CodaBaseDto
from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import ContractYearDto
from coda.apps.publishers.models import Publisher
from coda.apps.wizard import TemplateStep, Store
from coda.domain.publication import Monograph


class PublisherStepDto(CodaBaseDto):
    publisher: int
    contracts: list[ContractYearDto]

    @classmethod
    def from_monograph(self, monograph: Monograph) -> "PublisherStepDto":
        contracts = [ContractYearDto.from_contract_year(c) for c in monograph.contracts]
        return PublisherStepDto(publisher=monograph.publisher, contracts=contracts)

    def page_input(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            **to_htmx_formset_data(
                [{"contract": c.contract, "year": c.year} for c in self.contracts]
            ),
        }


class PublisherStep(TemplateStep):
    template_name = "fundingrequests/fundingrequest_monograph_publisher_and_contract.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        ctx["publisher_error"] = store.get("publisher_error", None)

        if request.POST.get("publisher"):
            publisher = Publisher.objects.get(pk=request.POST["publisher"])
            ctx["selected_publisher"] = publisher
            ctx["publishers"] = [publisher]
            ctx["contract_formset"] = ContractFormset(request.POST)
        elif store.get("publisher_step"):
            dto = PublisherStepDto(**store["publisher_step"])
            publisher = Publisher.objects.get(pk=dto.publisher)
            ctx["selected_publisher"] = publisher
            ctx["publishers"] = [publisher]
            ctx["contract_formset"] = ContractFormset.from_data(
                [c.to_post_data() for c in dto.contracts]
            )
        else:
            ctx["contract_formset"] = ContractFormset()
            ctx["publishers"] = Publisher.objects.none()

        return ctx

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        publisher_valid = bool(request.POST.get("publisher"))
        contract_formset = ContractFormset(request.POST)
        contract_formset_valid = contract_formset.is_valid()
        if not publisher_valid:
            store["publisher_error"] = "Please search and select a publisher."
        else:
            store["publisher_error"] = None
        return publisher_valid and contract_formset_valid

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = ContractFormset(request.POST)
        contracts = [
            ContractYearDto.from_contract_year(c) for c in contract_formset.contract_years()
        ]
        dto = PublisherStepDto(publisher=request.POST["publisher"], contracts=contracts)
        store["publisher_step"] = dto.to_post_data()
        store.save()


@login_required
def find_publisher(request: HttpRequest) -> HttpResponse:
    publishers = Publisher.objects.filter(name__icontains=request.POST["publisher_name"])
    return render(
        request,
        "fundingrequests/partials/publisher_search_results.html",
        {"publishers": publishers},
    )


@require_POST
def clear_publisher_error(request: HttpRequest) -> HttpResponse:
    publisher_name = request.POST.get("publisher_name", "") or request.GET.get("publisher_name", "")
    return render(
        request,
        "fundingrequests/partials/clear_publisher_error.html",
        {"publisher_name": publisher_name},
    )
