from django.urls import path

from coda.apps.invoices.views.create import create_invoice
from coda.apps.invoices.views.creditor import (
    CreditorCreateView,
    CreditorDetailView,
    CreditorListView,
    CreditorUpdateView,
)
from coda.apps.invoices.views.finances_home import finances_home
from coda.apps.invoices.views.fundingsources import (
    fundingsource_createview,
    fundingsource_detailview,
    fundingsource_listview,
    fundingsource_updateview,
)
from coda.apps.invoices.views.inspect import (
    add_conversion,
    add_conversion_dialog,
    delete_conversion,
    edit_conversion_row,
    invoice_detail,
    invoice_list,
    update_conversion,
)
from coda.apps.invoices.views.position_list import (
    add_position,
    invoice_total,
    remove_position,
    switch_position_tab,
)
from coda.apps.invoices.views.search import search_contracts, search_publications
from coda.apps.invoices.views.update import update_invoice

app_name = "invoices"

urlpatterns = [
    path("", finances_home, name="home"),
    path("list/", invoice_list, name="list"),
    path("<int:pk>/", invoice_detail, name="detail"),
    path("create/", create_invoice, name="create"),
    path("create/search-publications/", search_publications, name="pub_search"),
    path("create/search-contracts/", search_contracts, name="contract_search"),
    path("create/tab-switch/", switch_position_tab, name="tab_switch"),
    path("create/add-position/", add_position, name="add_position"),
    path("create/remove-position/", remove_position, name="remove_position"),
    path("create/total/", invoice_total, name="get_total"),
    path("update/<int:pk>/", update_invoice, name="update"),
    path("creditors/", CreditorListView.as_view(), name="creditor_list"),
    path("creditors/<int:pk>/", CreditorDetailView.as_view(), name="creditor_detail"),
    path("creditors/create/", CreditorCreateView.as_view(), name="creditor_create"),
    path("creditors/<int:pk>/update/", CreditorUpdateView.as_view(), name="creditor_update"),
    path("fundingsources/", fundingsource_listview, name="fundingsource_list"),
    path("fundingsources/<int:pk>/", fundingsource_detailview, name="fundingsource_detail"),
    path("fundingsources/create/", fundingsource_createview, name="fundingsource_create"),
    path("fundingsources/update/<int:pk>", fundingsource_updateview, name="fundingsource_update"),
    path("conversions/dialog/<int:pk>", add_conversion_dialog, name="add_conversion_dialog"),
    path("conversions/add/<int:pk>", add_conversion, name="add_conversion"),
    path("conversions/<int:pk>/edit/", edit_conversion_row, name="edit_conversion"),
    path("conversions/<int:pk>/update/", update_conversion, name="update_conversion"),
    path("conversions/<int:pk>/delete/", delete_conversion, name="delete_conversion"),
]
