from django.urls import path

from coda.apps.invoices.views.create import create_invoice
from coda.apps.invoices.views.inspect import invoice_detail, invoice_list
from coda.apps.invoices.views.creditor import (
    CreditorListView,
    CreditorDetailView,
    CreditorCreateView,
    CreditorUpdateView,
)

app_name = "invoices"

urlpatterns = [
    path("", invoice_list, name="list"),
    path("<int:pk>/", invoice_detail, name="detail"),
    path("create/", create_invoice, name="create"),
    path("creditors/", CreditorListView.as_view(), name="creditor_list"),
    path("creditors/<int:pk>/", CreditorDetailView.as_view(), name="creditor_detail"),
    path("creditors/create/", CreditorCreateView.as_view(), name="creditor_create"),
    path("creditors/<int:pk>/update/", CreditorUpdateView.as_view(), name="creditor_update"),
]
