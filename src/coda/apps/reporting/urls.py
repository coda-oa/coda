from django.urls import path

from coda.apps.reporting.views.home import reporting_home

app_name = "reporting"

urlpatterns = [
    path("", reporting_home, name="home"),
]
