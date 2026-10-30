from django.urls import path

from . import views

app_name = "preferences"
urlpatterns = [
    path("", views.GlobalPreferencesUpdateView.as_view(), name="global_preferences"),
    path(
        "crossref/",
        views.CrossrefSettingsUpdateView.as_view(),
        name="crossref_settings",
    ),
    path(
        "crossref-token-status/",
        views.crossref_token_status,
        name="crossref_token_status",
    ),
]
