from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from coda.apps.invoices.forms import CreditorForm
from coda.apps.invoices.models import Creditor


class CreditorListView(LoginRequiredMixin, ListView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/list.html"
    context_object_name = "creditors"


class CreditorDetailView(LoginRequiredMixin, DetailView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/detail.html"
    context_object_name = "creditor"


class CreditorCreateView(LoginRequiredMixin, CreateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore


class CreditorUpdateView(LoginRequiredMixin, UpdateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"  # type: ignore
