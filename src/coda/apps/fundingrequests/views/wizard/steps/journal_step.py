import logging
from typing import Any

from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.fundingrequests.views.wizard.formrestore import restore_formset
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.publications.dto import ContractYearDto
from coda.apps.wizard import Step, Store


class JournalStep(Step):
    template_name: str = "fundingrequests/fundingrequest_journal.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        title = request.POST.get("journal_title", None)
        journal_id = store.get("journal", None)
        if title:
            journals = find_by_title(title)
            ctx["journals"] = journals
            ctx["journal_title"] = title
        elif journal_id:
            selected_journal = get_object_or_404(Journal, pk=journal_id)
            ctx["selected_journal"] = selected_journal
            ctx["journal_title"] = selected_journal.title
            ctx["journals"] = [selected_journal]

        contract_dtos = [ContractYearDto(**c).to_post_data() for c in store.get("contracts", [])]
        ctx["contract_formset"] = restore_formset(
            ContractFormset, request, store_data=contract_dtos, prefix="contracts"
        )

        return ctx

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return bool(request.POST.get("journal")) and self._get_contractformset(request).is_valid()

    def _get_contractformset(self, request: HttpRequest) -> ContractFormset:
        formset = ContractFormset(request.POST, prefix="contracts")
        return formset

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = self._get_contractformset(request)

        store["journal"] = request.POST["journal"]
        store["contracts"] = [
            ContractYearDto.from_contract_year(c).to_post_data()
            for c in contract_formset.contract_years()
        ]

        logging.info(
            f"Journal step done. Journal: {store['journal']}, Contracts: {store['contracts']}"
        )

        store.save()
