from django.urls import path

from coda.apps.opencost.views import (
    report_list_view,
    generate_report,
    download_xml,
)

app_name = "opencost"

urlpatterns = [
    path("", view=report_list_view, name="list"),
    path("generate/", generate_report, name="generate"),
    path("<int:report_id>/download/", download_xml, name="download"),
]
