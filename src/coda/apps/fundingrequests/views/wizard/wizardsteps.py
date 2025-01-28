from typing import Any, TypeVar

from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from coda.apps.authors.forms import AuthorForm
from coda.apps.formbase import CodaFormBase
from coda.apps.fundingrequests.forms import ContractFormset, ExternalFundingFormset, PaymentForm
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.publications.dto import ContractYearDto
from coda.apps.wizard import FormStep, Step, Store

_TForm = TypeVar("_TForm", bound=CodaFormBase, covariant=True)


def form_with_post_or_store_data(
    form_type: type[_TForm],
    request: HttpRequest,
    store_data: dict[str, Any] | None,
    **kwargs: Any,
) -> _TForm:
    """
    Create a form instance with POST data if matching keys are present, otherwise use stored data.
    If no stored data is present, create an empty form instance.
    """
    if form_type.form_posted(request.POST):
        return form_type(request.POST, **kwargs)
    elif store_data:
        return form_type(store_data, **kwargs)
    else:
        return form_type(**kwargs)


class SubmitterStep(FormStep):
    template_name: str = "fundingrequests/fundingrequest_submitter.html"
    form_class = AuthorForm

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return super().get_context_data(request, store) | {
            "form": form_with_post_or_store_data(self.form_class, request, store.get("submitter")),
            "submitter": store.get("submitter"),
        }

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        form = AuthorForm(request.POST)
        valid = form.is_valid()
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        form = AuthorForm(request.POST)
        form.full_clean()
        store["submitter"] = form.to_dto().to_post_data()


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

        if request.POST.get("contracts-total_forms"):
            ctx["contract_formset"] = ContractFormset(request.POST, prefix="contracts")
        else:
            contracts = [ContractYearDto(**c) for c in store.get("contracts", [])]
            ctx["contract_formset"] = ContractFormset.from_data(
                [c.to_post_data() for c in contracts], prefix="contracts"
            )

        return ctx

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return (
            bool(request.POST.get("journal"))
            and ContractFormset(request.POST, prefix="contracts").is_valid()
        )

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = ContractFormset(request.POST)

        store["journal"] = request.POST["journal"]
        store["contracts"] = [
            ContractYearDto.from_contract_year(c).to_post_data()
            for c in contract_formset.contract_years()
        ]
        store.save()


class FundingStep(Step):
    template_name: str = "fundingrequests/fundingrequest_funding.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        context = super().get_context_data(request, store)
        context["cost_form"] = form_with_post_or_store_data(PaymentForm, request, store.get("cost"))
        context["funding_formset"] = self._restore_formset(request, store)
        return context

    def _restore_formset(self, request: HttpRequest, store: Store) -> ExternalFundingFormset:
        if request.POST.get("total_forms"):
            return ExternalFundingFormset(request.POST)
        elif store.get("funding"):
            return ExternalFundingFormset.from_data(store["funding"])
        else:
            return ExternalFundingFormset()

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        cost_form = PaymentForm(request.POST)
        funding_formset = ExternalFundingFormset(request.POST)
        funding_valid = funding_formset.is_valid() or funding_formset.is_empty()
        return cost_form.is_valid() and funding_valid

    def done(self, request: HttpRequest, store: Store) -> None:
        cost_form = PaymentForm(request.POST)
        cost_form.full_clean()
        cost = cost_form.to_dto()
        store["cost"] = cost.to_post_data()

        funding_formset = ExternalFundingFormset(request.POST)
        dto = funding_formset.to_dto_list()
        store["funding"] = list(d.to_post_data() for d in dto) if dto else None
        store.save()
