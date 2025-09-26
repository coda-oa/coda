from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.invoices import repository
from coda.apps.invoices.forms import CreditorForm
from coda.apps.invoices.models import Creditor
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.invoice import CreditorId


class CreditorListView(LoginRequiredMixin, SimpleSearchEntityListView[Creditor]):
    model = Creditor
    paginate_by = 20
    entity_name = "Creditors"   
    entity_create_url = "invoices:creditor_create"
    entity_list_item_template = "invoices/creditors/list.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True 

class CreditorDetailView(LoginRequiredMixin, DetailView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        invoices = repository.get_by_creditor(CreditorId(self.object.id))

        return super().get_context_data(**kwargs) | {"creditor": self.object, "invoices": invoices}


class CreditorCreateView(LoginRequiredMixin, CreateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore


class CreditorUpdateView(LoginRequiredMixin, UpdateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore
