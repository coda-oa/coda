from django.urls import path

from coda.apps.invoices.views.create import (
    create_invoice,
    creditor_create_modal,
    creditor_create_modal_submit,
)
from coda.apps.invoices.views.creditor import (
    CreditorCreateView,
    CreditorDetailView,
    CreditorListView,
    CreditorUpdateView,
    archive_creditor,
    delete_creditor,
    request_archive_creditor,
    request_delete_creditor,
    request_restore_creditor,
    restore_creditor,
)
from coda.apps.invoices.views.finances_home import finances_home
from coda.apps.invoices.views.fundingsources import (
    fundingsource_createview,
    fundingsource_detailview,
    fundingsource_listview,
    fundingsource_updateview,
)
from coda.apps.invoices.views.importview import import_invoices_view
from coda.apps.invoices.views.inspect import (
    invoice_detail,
    invoice_list,
    load_conversion_section,
    pay_invoice,
    position_cost_type_options,
)
from coda.apps.invoices.views.position_views import (
    add_position,
    invoice_total,
    remove_position,
    switch_position_tab,
)
from coda.apps.invoices.views.funding_assignment_views import (
    add_funding_assignment,
    refresh_unassigned_costs,
    remove_funding_assignment,
    switch_cost_basis_mode,
    switch_funding_source_type,
)
from coda.apps.invoices.views.search import search_contracts, search_publications
from coda.apps.invoices.views.update import free_position_cost_type_options, update_invoice

app_name = "invoices"

urlpatterns = [
    path("", finances_home, name="finances_home"),
    path("list/", invoice_list, name="list"),
    path("<int:pk>/", invoice_detail, name="detail"),
    path("create/", create_invoice, name="create"),
    path("create/search-publications/", search_publications, name="pub_search"),
    path("create/search-contracts/", search_contracts, name="contract_search"),
    path("create/tab-switch/", switch_position_tab, name="tab_switch"),
    path("create/add-position/", add_position, name="add_position"),
    path("create/remove-position/", remove_position, name="remove_position"),
    path(
        "create/add-funding-asssignment",
        add_funding_assignment,
        name="position_add_funding_assignment",
    ),
    path(
        "create/remove-funding-asssignment",
        remove_funding_assignment,
        name="position_remove_funding_assignment",
    ),
    path(
        "create/refresh-funding-asssignment",
        refresh_unassigned_costs,
        name="position_refresh_funding_assignment",
    ),
    path(
        "create/switch-cost-basis-mode",
        switch_cost_basis_mode,
        name="position_switch_cost_basis_mode",
    ),
    path(
        "create/switch_funding_source_type",
        switch_funding_source_type,
        name="switch_funding_source_type",
    ),
    path("create/total/", invoice_total, name="get_total"),
    path("update/<int:pk>/", update_invoice, name="update"),
    path("creditors/", CreditorListView.as_view(), name="creditor_list"),
    path("creditors/<int:pk>/", CreditorDetailView.as_view(), name="creditor_detail"),
    path("creditors/create/", CreditorCreateView.as_view(), name="creditor_create"),
    path("creditors/<int:pk>/update/", CreditorUpdateView.as_view(), name="creditor_update"),
    path(
        "creditors/<int:pk>/request-archive/",
        request_archive_creditor,
        name="creditor_request_archive",
    ),
    path("creditors/<int:pk>/archive/", archive_creditor, name="creditor_archive"),
    path(
        "creditors/<int:pk>/request-delete/",
        request_delete_creditor,
        name="creditor_request_delete",
    ),
    path("creditors/<int:pk>/delete/", delete_creditor, name="creditor_delete"),
    path(
        "creditors/<int:pk>/request-restore/",
        request_restore_creditor,
        name="creditor_request_restore",
    ),
    path("creditors/<int:pk>/restore/", restore_creditor, name="creditor_restore"),
    path("fundingsources/", fundingsource_listview, name="fundingsource_list"),
    path("fundingsources/<int:pk>/", fundingsource_detailview, name="fundingsource_detail"),
    path("fundingsources/create/", fundingsource_createview, name="fundingsource_create"),
    path("fundingsources/update/<int:pk>", fundingsource_updateview, name="fundingsource_update"),
    path("conversion_section/", load_conversion_section, name="conversions_section"),
    path("<int:pk>/pay/", pay_invoice, name="pay_invoice"),
    path("import/", import_invoices_view, name="import"),
    path(
        "position-cost-type-options/", position_cost_type_options, name="position_cost_type_options"
    ),
    path(
        "free-position-cost-type-options/",
        free_position_cost_type_options,
        name="free_position_cost_type_options",
    ),
    path("creditor-create-modal/", creditor_create_modal, name="creditor_create_modal"),
    path(
        "creditor-create-modal/submit/",
        creditor_create_modal_submit,
        name="creditor_create_modal_submit",
    ),
]
