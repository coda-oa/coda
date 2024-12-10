from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from pydantic import Field

from coda.apps.dto import CodaBaseDto
from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publishers.models import Publisher
from coda.apps.wizard import Step, Store


class PublisherStepDto(CodaBaseDto):
    publisher: int
    contracts: list[int] = Field(default_factory=list)

    def page_input(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            **to_htmx_formset_data([{"contract": c} for c in self.contracts]),
        }


class PublisherStep(Step):
    template_name = "fundingrequests/fundingrequest_monograph_publisher_and_contract.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        return ctx | {
            "contract_formset": ContractFormset(),
            "publishers": Publisher.objects.none(),
        }

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return bool(request.POST.get("publisher"))

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = ContractFormset(request.POST)
        contracts = [c["contract"].pk for c in contract_formset.data]
        dto = PublisherStepDto(publisher=request.POST["publisher"], contracts=contracts)
        store["publisher_step"] = dto.to_post_data()
        store.save()


def find_publisher(request: HttpRequest) -> HttpResponse:
    publishers = Publisher.objects.filter(name__icontains=request.POST["publisher_name"])
    return render(
        request,
        "fundingrequests/partials/publisher_search_results.html",
        {"publishers": publishers},
    )
