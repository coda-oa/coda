import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, TemplateView

from coda.apps.contracts.forms import ContractForm, EntityFormset
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.contracts.services import contract_create
from coda.contract import Contract, PublisherId
from coda.date import DateRange
from coda.publication import JournalId
from coda.string import NonEmptyStr


class ContractListView(LoginRequiredMixin, ListView[ContractModel]):
    model = ContractModel
    template_name = "contracts/contract_list.html"
    queryset = ContractModel.objects.all()
    context_object_name = "contracts"


class ContractCreateView(LoginRequiredMixin, TemplateView):
    template_name = "contracts/contract_create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Contract"} | self.get_forms()

    def get_forms(self) -> dict[str, Any]:
        if self.request.method == "POST":
            contract_form = ContractForm(self.request.POST)
            publisher_formset = EntityFormset(
                self.request.POST, form_id="publishers-formset", prefix="publishers"
            )
            journal_formset = EntityFormset(
                self.request.POST, form_id="journals-formset", prefix="journals"
            )
        else:
            contract_form = ContractForm()
            publisher_formset = EntityFormset(prefix="publishers", form_id="publishers-formset")
            journal_formset = EntityFormset(prefix="journals", form_id="journals-formset")

        return {
            "contract_form": contract_form,
            "publisher_formset": publisher_formset,
            "journal_formset": journal_formset,
        }

    def post(self, request: HttpRequest) -> HttpResponse:
        contract_form = ContractForm(request.POST)
        publisher_formset = EntityFormset(request.POST, prefix="publishers")
        journal_formset = EntityFormset(request.POST, prefix="journals")
        forms: list[ContractForm | EntityFormset] = [
            contract_form,
            publisher_formset,
            journal_formset,
        ]
        if all(form.is_valid() for form in forms):
            return self.form_valid(contract_form, publisher_formset, journal_formset)

        logging.error("CONTRACT FORM")
        logging.error(contract_form.errors.as_text())

        logging.error("PUBLISHER FORMSET")
        for form in publisher_formset.forms:
            logging.error(form.errors.as_text())

        logging.error("JOURNAL FORMSET")
        for form in journal_formset.forms:
            logging.error(form.errors.as_text())
        return render(request, self.template_name, self.get_context_data())

    def form_valid(
        self, form: ContractForm, publisher_formset: EntityFormset, journal_formset: EntityFormset
    ) -> HttpResponse:
        form_data = form.cleaned_data
        period = DateRange.create(
            start=form_data.pop("start_date", None), end=form_data.pop("end_date", None)
        )

        publishers = [PublisherId(d["entity_id"]) for d in publisher_formset.data]
        journals = [JournalId(d["entity_id"]) for d in journal_formset.data]

        contract = Contract.new(NonEmptyStr(form_data["name"]), publishers, period, journals)
        contract_id = contract_create(contract)
        return redirect("contracts:detail", contract_id)


@login_required
def contract_detail(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(ContractModel, pk=pk)
    return render(request, "contracts/contract_detail.html", {"contract": contract})
