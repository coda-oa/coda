from django.urls import path

from coda.apps.invoices.views.create import create_invoice
from coda.apps.invoices.views.inspect import invoice_detail, invoice_list

app_name = "invoices"

urlpatterns = [
    path("", invoice_list, name="list"),
    path("<int:pk>/", invoice_detail, name="detail"),
    path("create/", create_invoice, name="create"),
]
