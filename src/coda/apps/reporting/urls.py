from django.urls import path

from coda.apps.reporting.views.home import reporting_home
from coda.apps.reporting.views.page import reporting_page, reporting_region

app_name = "reporting"

urlpatterns = [
    path("", reporting_home, name="home"),
    path("stats/fundingrequests/", reporting_page, name="stats_fundingrequests"),
    path(
        "stats/fundingrequests/region/",
        reporting_region,
        name="stats_fundingrequests_region",
    ),
]
