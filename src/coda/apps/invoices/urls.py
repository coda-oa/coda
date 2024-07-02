from django.urls import path

from coda.apps.invoices.views.create import (
    add_position,
    create_invoice,
    get_total,
    remove_position,
    search_publications,
)
from coda.apps.invoices.views.creditor import (
    CreditorCreateView,
    CreditorDetailView,
    CreditorListView,
    CreditorUpdateView,
)
from coda.apps.invoices.views.inspect import invoice_detail, invoice_list

app_name = "invoices"

urlpatterns = [
    path("", invoice_list, name="list"),
    path("<int:pk>/", invoice_detail, name="detail"),
    path("create/", create_invoice, name="create"),
    path("create/search-publications/", search_publications, name="pub_search"),
    path("create/add-position/", add_position, name="add_position"),
    path("create/remove-position/", remove_position, name="remove_position"),
    path("create/total/", get_total, name="get_total"),
    path("creditors/", CreditorListView.as_view(), name="creditor_list"),
    path("creditors/<int:pk>/", CreditorDetailView.as_view(), name="creditor_detail"),
    path("creditors/create/", CreditorCreateView.as_view(), name="creditor_create"),
    path("creditors/<int:pk>/update/", CreditorUpdateView.as_view(), name="creditor_update"),
]
