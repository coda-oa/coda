from django.urls import path

from coda.apps.journals.views import (
    journal_create_view,
    journal_detail_view,
    journal_list_view,
    journal_update_view,
)

app_name = "journals"
urlpatterns = [
    path("", view=journal_list_view, name="list"),
    path("create/", view=journal_create_view, name="create"),
    path("update/<str:eissn>/", view=journal_update_view, name="update"),
    path("<str:eissn>/", view=journal_detail_view, name="detail"),
]
