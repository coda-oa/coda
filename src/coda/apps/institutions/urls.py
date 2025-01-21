from django.urls import path

from . import views

app_name = "institutions"

urlpatterns = [
    path("", views.institution_list_view, name="list"),
    path("toggle-selectable/<int:pk>", views.toggle_selectable, name="toggle_selectable"),
]
