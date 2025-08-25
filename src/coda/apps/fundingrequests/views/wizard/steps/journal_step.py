import logging
from typing import Any

from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.fundingrequests.views.wizard.steps.composed_step import ComposedStep
from coda.apps.fundingrequests.views.wizard.steps.contract_step import ContractStep
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.wizard import Store, TemplateStep


class JournalContractStep(ComposedStep):
    def __init__(self) -> None:
        super().__init__()
        self.substeps = [JournalStep(), ContractStep()]


class JournalStep(TemplateStep):
    template_name: str = "fundingrequests/fundingrequest_journal.html"

    def __init__(self) -> None:
        self.journal_error: str | None = None

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        title = request.POST.get("journal_title", None)
        journal_id = store.get("journal", None)
        ctx["journal_error"] = self.journal_error
        if title:
            journals = find_by_title(title)
            ctx["journals"] = journals
            ctx["journal_title"] = title
        elif journal_id:
            selected_journal = get_object_or_404(Journal, pk=journal_id)
            ctx["selected_journal"] = selected_journal
            ctx["journal_title"] = selected_journal.title
            ctx["journals"] = [selected_journal]

        return ctx

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        journal_valid = bool(request.POST.get("journal"))
        contract_formset = self._get_contractformset(request)
        contract_formset_valid = contract_formset.is_valid()
        if not journal_valid:
            self.journal_error = "Please search and select a journal."
        return journal_valid and contract_formset_valid

    def _get_contractformset(self, request: HttpRequest) -> ContractFormset:
        formset = ContractFormset(request.POST, prefix="contracts")
        return formset

    def done(self, request: HttpRequest, store: Store) -> None:
        store["journal"] = request.POST["journal"]
        store.save()
        logging.info(f"Journal step done. Journal: {store['journal']}")
