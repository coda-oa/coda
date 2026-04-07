import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render

from coda.apps.fundingrequests.forms import ContractFormset
from coda.apps.fundingrequests.views.wizard.steps.composed_step import ComposedStep
from coda.apps.fundingrequests.views.wizard.steps.contract_step import ContractStep
from coda.apps.journals.models import Journal
from coda.apps.journals import services as journal_services
from coda.apps.wizard import Store, TemplateStep

from django.views.decorators.http import require_POST


class JournalContractStep(ComposedStep):
    def __init__(self) -> None:
        super().__init__()
        self.substeps = [JournalStep(), ContractStep()]


class JournalStep(TemplateStep):
    template_name: str = "fundingrequests/fundingrequest_journal.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        title = request.POST.get("journal_title", None)
        journal_id = store.get("journal", None)
        ctx["journal_error"] = store.get("journal_error", None)
        if title:
            journals = journal_services.find_by_title(title)
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
            store["journal_error"] = "Please search and select a journal."
        else:
            store["journal_error"] = None
        return journal_valid and contract_formset_valid

    def _get_contractformset(self, request: HttpRequest) -> ContractFormset:
        formset = ContractFormset(request.POST, prefix="contracts")
        return formset

    def done(self, request: HttpRequest, store: Store) -> None:
        store["journal"] = request.POST["journal"]
        store.save()
        logging.info(f"Journal step done. Journal: {store['journal']}")


@require_POST
def clear_journal_error(request: HttpRequest) -> HttpResponse:
    journal_title = request.POST.get("journal_title", "")
    return render(
        request,
        "fundingrequests/partials/clear_journal_error.html",
        {"journal_title": journal_title},
    )


@login_required
def find_journal(request: HttpRequest) -> HttpResponse:
    search_term = request.POST.get("journal_title", "")
    journals = journal_services.find_by_title(search_term)
    return render(
        request,
        "fundingrequests/partials/journal_search_results.html",
        {
            "journals": journals,
            "search_term": search_term,
            "row_template": "fundingrequests/partials/journal_row.html",
        },
    )
