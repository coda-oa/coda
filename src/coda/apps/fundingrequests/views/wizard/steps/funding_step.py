from coda.apps.fundingrequests.forms import ExternalFundingFormset, PaymentForm
from coda.apps.fundingrequests.views.wizard.formrestore import (
    restore_form,
    restore_formset,
)
from coda.apps.wizard import Step, Store


from django.http import HttpRequest


from typing import Any


class FundingStep(Step):
    template_name: str = "fundingrequests/fundingrequest_funding.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        context = super().get_context_data(request, store)
        context["cost_form"] = restore_form(PaymentForm, request, store.get("cost"))
        context["funding_formset"] = restore_formset(
            ExternalFundingFormset, request, store_data=store.get("funding")
        )
        return context

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
