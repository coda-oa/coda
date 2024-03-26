from django.urls import path

from coda.apps.contracts.views import ContractCreateView, ContractListView

app_name = "contracts"
urlpatterns = [
    path("", ContractListView.as_view(), name="list"),
    path("create/", ContractCreateView.as_view(), name="create"),
]
