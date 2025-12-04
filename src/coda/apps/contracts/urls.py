from django.urls import path

from coda.apps.contracts import partials
from coda.apps.contracts.forms import EntityFormset
from coda.apps.contracts.views import (
    ContractListView,
    contract_detail,
    edit_contract_view,
    add_contract_linkrow,
)

management_view = EntityFormset.get_management_view()

app_name = "contracts"
urlpatterns = [
    path("", ContractListView.as_view(), name="list"),
    path("create/", edit_contract_view, name="create"),
    path("update/<int:pk>/", edit_contract_view, name="update"),
    path("<int:pk>/", contract_detail, name="detail"),
    path(
        "partial/entity-form",
        management_view.as_view(),
        name=management_view.name.removeprefix("contracts:"),
    ),
    path("partial/search-publisher", partials.search_publisher, name="search_publisher"),
    path("partial/search-journal", partials.search_journal, name="search_journal"),
    path("partial/add-contract-linkrow/", add_contract_linkrow, name="partial_add_linkrow"),
]
