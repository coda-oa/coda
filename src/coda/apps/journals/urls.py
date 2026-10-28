from django.urls import path

from coda.apps.journals.views import (
    JournalCreateModalView,
    journal_create_view,
    journal_detail_view,
    journal_list_view,
    journal_update_view,
)

app_name = "journals"
urlpatterns = [
    path("", view=journal_list_view, name="list"),
    path("create/", view=journal_create_view, name="create"),
    path("create-modal/", view=JournalCreateModalView.as_view(), name="create_modal"),
    path("update/<int:pk>/", view=journal_update_view, name="update"),
    path("<int:pk>/", view=journal_detail_view, name="detail"),
]
