from django.urls import path

from coda.apps.journals.views import journal_detail_view, journal_list_view

app_name = "journals"
urlpatterns = [
    path("", view=journal_list_view, name="list"),
    path("<str:eissn>/", view=journal_detail_view, name="detail"),
]
