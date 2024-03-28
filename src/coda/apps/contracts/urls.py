from django.urls import path

from coda.apps.contracts.views import (
    ContractCreateView,
    ContractListView,
    change_contract_status,
    contract_detail,
)

app_name = "contracts"
urlpatterns = [
    path("", ContractListView.as_view(), name="list"),
    path("create/", ContractCreateView.as_view(), name="create"),
    path("<int:pk>/", contract_detail, name="detail"),
    path("<int:pk>/status/", change_contract_status, name="status"),
]
