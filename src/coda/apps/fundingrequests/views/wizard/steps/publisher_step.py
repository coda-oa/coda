from typing import Any

from django.http import HttpRequest

from coda.apps.dto import CodaBaseDto
from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.fundingrequests.views.wizard.steps._search_views import make_search_view
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import ContractYearDto
from coda.apps.publishers import services as publisher_services
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


find_publisher = make_search_view(
    param_name="publisher_name",
    search_fn=publisher_services.find_by_name_contains,
    results_key="publishers",
    results_template="fundingrequests/partials/publisher_search_results.html",
)
