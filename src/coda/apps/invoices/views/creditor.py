from django.views.generic import CreateView, DetailView, ListView, UpdateView

from coda.apps.invoices.forms import CreditorForm
from coda.apps.invoices.models import Creditor


class CreditorListView(ListView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/list.html"
    context_object_name = "creditors"


class CreditorDetailView(DetailView[Creditor]):
    model = Creditor
    template_name = "invoices/creditors/detail.html"
    context_object_name = "creditor"


class CreditorCreateView(CreateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"


class CreditorUpdateView(UpdateView[Creditor, CreditorForm]):
    model = Creditor
    template_name = "generic_form_view.html"
    fields = "__all__"
