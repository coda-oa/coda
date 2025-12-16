from django.urls import path

from coda.apps.opencost.views import (
    report_list_view,
    report_detail,
    generate_report_form,
    generate_report,
    download_xml,
    delete_report,
)

app_name = "opencost"

urlpatterns = [
    path("", view=report_list_view, name="list"),
    path("generate/", generate_report_form, name="generate"),
    path("generate/submit/", generate_report, name="generate_submit"),
    path("<int:report_id>/", report_detail, name="detail"),
    path("<int:report_id>/download/", download_xml, name="download"),
    path("<int:report_id>/delete/", delete_report, name="delete"),
]
