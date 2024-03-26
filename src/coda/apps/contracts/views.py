from django.forms import ModelForm
from django.views.generic import CreateView, ListView

from coda.apps.contracts.models import Contract


class ContractListView(ListView[Contract]):
    model = Contract
    template_name = "contracts/contract_list.html"
    context_object_name = "contracts"


class ContractCreateView(CreateView[Contract, ModelForm[Contract]]):
    model = Contract
    fields = ["name", "publishers", "start_date", "end_date", "is_active"]
    template_name = "generic_form_view.html"
