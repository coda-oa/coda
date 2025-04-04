from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from coda.apps.invoices import repository
from coda.apps.invoices.forms import CreditorForm
from coda.apps.invoices.models import Creditor
from coda.domain.invoice import CreditorId


class CreditorListView(LoginRequiredMixin, ListView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/list.html"
    context_object_name = "creditors"


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
