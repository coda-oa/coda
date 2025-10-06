from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.invoices import repository
from coda.apps.invoices.forms import CreditorForm
from coda.apps.invoices.models import Creditor
from coda.apps.views import SimpleSearchEntityListView
from coda.domain.invoice import CreditorId

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Creditors", parent_url_name="invoices:finances_home")
class CreditorListView(LoginRequiredMixin, SimpleSearchEntityListView[Creditor]):
    model = Creditor
    paginate_by = 20
    entity_name = "Creditors"
    entity_create_url = "invoices:creditor_create"
    entity_list_item_template = "invoices/creditors/list.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True


@breadcrumb("Creditor Detail", parent_url_name="invoices:creditor_list")
class CreditorDetailView(LoginRequiredMixin, DetailView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        invoices = repository.get_by_creditor(CreditorId(self.object.id))

        return super().get_context_data(**kwargs) | {"creditor": self.object, "invoices": invoices}


@breadcrumb("Create Creditor", parent_url_name="invoices:creditor_list")
class CreditorCreateView(LoginRequiredMixin, CreateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore


@breadcrumb("Edit Creditor", parent_url_name="invoices:creditor_detail")
class CreditorUpdateView(LoginRequiredMixin, UpdateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore
