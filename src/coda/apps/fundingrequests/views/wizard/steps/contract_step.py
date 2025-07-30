from typing import Any, cast

from django.http import HttpRequest

from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.fundingrequests.views.wizard.formrestore import restore_formset
from coda.apps.publications.dto import ContractYearDto
from coda.apps.wizard import Store, TemplateStep


class ContractStep(TemplateStep):
    template_name: str = "fundingrequests/fundingrequest_contract_step.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        contract_formset = self.get_contract_formset(request, store)
        inactive_contracts_selected = contract_formset.any_inactive_contracts_selected()
        ctx: dict[str, Any] = {"contract_formset": contract_formset}

        if "include_inactive" in request.POST or inactive_contracts_selected:
            ctx["include_inactive"] = "true"

        return ctx

    def get_contract_formset(self, request: HttpRequest, store: Store) -> ContractFormset:
        return cast(
            ContractFormset,
            restore_formset(
                ContractFormset,
                request,
                store_data=store.get("contracts"),
                prefix="contracts",
            ),
        )

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        formset = self.get_contract_formset(request, store)
        return formset.is_valid()

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = self.get_contract_formset(request, store)
        store["contracts"] = [
            ContractYearDto.from_contract_year(c).to_post_data()
            for c in contract_formset.contract_years()
        ]
        store.save()
