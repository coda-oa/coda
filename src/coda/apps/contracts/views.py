from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import FormView, ListView

from coda.apps.contracts.forms import ContractForm
from coda.apps.contracts.models import Contract
from coda.apps.contracts.services import DateRange, contract_create


class ContractListView(LoginRequiredMixin, ListView[Contract]):
    model = Contract
    template_name = "contracts/contract_list.html"
    queryset = Contract.objects.all()
    context_object_name = "contracts"


class ContractCreateView(LoginRequiredMixin, FormView[ContractForm]):
    form_class = ContractForm
    template_name = "generic_form_view.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"title": "Create Contract"}

    def form_valid(self, form: ContractForm) -> HttpResponse:
        form_data = form.cleaned_data
        date_range = DateRange(
            start_date=form_data.pop("start_date", None), end_date=form_data.pop("end_date", None)
        )
        contract = contract_create(**form_data, date_range=date_range)
        return redirect("contracts:detail", contract.pk)


@login_required
def contract_detail(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, "contracts/contract_detail.html", {"contract": contract})
