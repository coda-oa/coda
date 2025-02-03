from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.fundingrequests.views.wizard.formrestore import restore_formset
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.publications.dto import ContractYearDto
from coda.apps.wizard import Step, Store


from django.http import HttpRequest
from django.shortcuts import get_object_or_404


from typing import Any


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
        return (
            bool(request.POST.get("journal"))
            and ContractFormset(request.POST, prefix="contracts").is_valid()
        )

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = ContractFormset(request.POST, prefix="contracts")

        store["journal"] = request.POST["journal"]
        store["contracts"] = [
            ContractYearDto.from_contract_year(c).to_post_data()
            for c in contract_formset.contract_years()
        ]

        store.save()
