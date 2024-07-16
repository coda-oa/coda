from django.urls import path

from . import views

app_name = "preferences"
urlpatterns = [
    path("", views.GlobalPreferencesUpdateView.as_view(), name="global_preferences"),
]
