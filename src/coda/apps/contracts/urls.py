from django.urls import path

from coda.apps.contracts.views import ContractCreateView, ContractListView, contract_detail

app_name = "contracts"
urlpatterns = [
    path("", ContractListView.as_view(), name="list"),
    path("create/", ContractCreateView.as_view(), name="create"),
    path("<int:pk>/", contract_detail, name="detail"),
]
