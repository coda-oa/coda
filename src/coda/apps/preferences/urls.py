from django.urls import path

from . import views

app_name = "preferences"
urlpatterns = [
    path("", views.GlobalPreferencesUpdateView.as_view(), name="global_preferences"),
    path("vocabularies/", views.vocabulary_view, name="vocabulary"),
    path("vocabulary/select/", views.select_vocabulary, name="select_vocabulary"),
    path("vocabulary/edit/move-to-forbidden", views.move_to_forbidden, name="move_to_forbidden"),
    path("vocabulary/edit/move-to-allow", views.move_to_allowed, name="move_to_allowed"),
]
