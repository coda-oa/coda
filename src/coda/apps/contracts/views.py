import datetime
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
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
    form_class = ContractForm
    template_name = "contracts/contract_create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Contract"} | self.get_forms()

    def get_forms(self) -> dict[str, Any]:
        if self.request.method == "POST":
            contract_form = ContractForm(self.request.POST)
            publisher_formset = EntityFormset(
                self.request.POST, prefix="publishers", table_classes="article__table"
            )
            journal_formset = EntityFormset(
                self.request.POST, prefix="journals", table_classes="article__table"
            )
        else:
            contract_form = ContractForm()
            publisher_formset = EntityFormset(prefix="publishers", table_classes="article__table")
            journal_formset = EntityFormset(prefix="journals", table_classes="article__table")

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

        return self.get(request)

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


@login_required
@require_POST
def change_contract_status(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(ContractModel, pk=pk)
    status = request.POST["status"]
    if status == "active":
        contract.make_active(until=_until(request))
    elif status == "inactive":
        contract.make_inactive()

    return redirect("contracts:detail", contract.pk)


def _until(request: HttpRequest) -> datetime.date | None:
    return datetime.date.fromisoformat(request.POST["until"]) if "until" in request.POST else None
