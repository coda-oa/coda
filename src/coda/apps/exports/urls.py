from django.urls import path

from coda.apps.exports.views.contract_csv_views import (
    contract_csv_delete_view,
    contract_csv_detail_page,
    contract_csv_export_create_view,
    contract_csv_export_list_view,
    contract_download_csv,
)
from coda.apps.exports.views.fundingrequest_csv_views import (
    fundingrequest_csv_delete_view,
    fundingrequest_csv_detail_page,
    fundingrequest_csv_export_create_view,
    fundingrequest_csv_export_list_view,
    fundingrequest_download_csv,
)
from coda.apps.exports.views.export_home import export_home

app_name = "exports"

urlpatterns = [
    path("", view=export_home, name="export_home"),
    path(
        "fundingrequests-csv/",
        view=fundingrequest_csv_export_list_view,
        name="fundingrequests_csv_list",
    ),
    path(
        "fundingrequests-csv/create/",
        view=fundingrequest_csv_export_create_view,
        name="fundingrequests_csv_create",
    ),
    path(
        "fundingrequests-csv/<int:pk>/",
        view=fundingrequest_csv_detail_page,
        name="fundingrequests_csv_detail",
    ),
    path(
        "fundingrequests-csv/<int:pk>/download/",
        view=fundingrequest_download_csv,
        name="fundingrequests_csv_download",
    ),
    path(
        "fundingrequests-csv/<int:pk>/delete/",
        view=fundingrequest_csv_delete_view,
        name="fundingrequests_csv_delete",
    ),
    path(
        "contracts-csv/",
        view=contract_csv_export_list_view,
        name="contracts_csv_list",
    ),
    path(
        "contracts-csv/create/",
        view=contract_csv_export_create_view,
        name="contracts_csv_create",
    ),
    path(
        "contracts-csv/<int:pk>/",
        view=contract_csv_detail_page,
        name="contracts_csv_detail",
    ),
    path(
        "contracts-csv/<int:pk>/download/",
        view=contract_download_csv,
        name="contracts_csv_download",
    ),
    path(
        "contracts-csv/<int:pk>/delete/",
        view=contract_csv_delete_view,
        name="contracts_csv_delete",
    ),
]
