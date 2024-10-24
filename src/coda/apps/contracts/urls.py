from django.urls import path

from coda.apps.contracts import partials
from coda.apps.contracts.forms import EntityFormset
from coda.apps.contracts.views import ContractCreateView, ContractListView, contract_detail

management_view = EntityFormset.get_management_view()

app_name = "contracts"
urlpatterns = [
    path("", ContractListView.as_view(), name="list"),
    path("create/", ContractCreateView.as_view(), name="create"),
    path("<int:pk>/", contract_detail, name="detail"),
    path(
        "partial/entity-form",
        management_view.as_view(),
        name=management_view.name.removeprefix("contracts:"),
    ),
    path("partial/search-publisher", partials.search_publisher, name="search_publisher"),
    path("partial/search-journal", partials.search_journal, name="search_journal"),
]
