"""URL configuration for exports app."""

from django.urls import path

from coda.apps.exports.views.fundingrequest_csv_views import (
    fundingrequest_csv_detail_page,
    fundingrequest_csv_export_create_view,
    fundingrequest_csv_export_list_view,
    fundingrequest_download_csv,
    fundingrequests_csv_delete,
)

app_name = "exports"

urlpatterns = [
    # Export menu/selector (future)
    # path('', views.export_menu, name='menu'),
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
        view=fundingrequests_csv_delete,
        name="fundingrequests_csv_delete",
    ),
    # OpenCost XML export (could be moved here from opencost app in future)
    # path('opencost/', ..., name='opencost'),
]
