from django.urls import path

from coda.apps.journals.views import journal_detail_view, journal_list_view, journal_create_view

app_name = "journals"
urlpatterns = [
    path("", view=journal_list_view, name="list"),
    path("create/", view=journal_create_view, name="create"),
    path("<str:eissn>/", view=journal_detail_view, name="detail"),
]
