from django.urls import path

from coda.apps.journals.views import journal_detail_view

app_name = "journals"
urlpatterns = [
    path("<str:journal>/", view=journal_detail_view, name="detail"),
]
