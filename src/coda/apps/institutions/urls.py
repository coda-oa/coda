from django.urls import path

from . import views

app_name = "institutions"

urlpatterns = [
    path("", views.institution_list_view, name="list"),
    path("create/", views.create_institution_view, name="create"),
    path("toggle-selectable/<int:pk>", views.toggle_selectable, name="toggle_selectable"),
    path("import/", views.import_view, name="import_view"),
    path("import-file/", views.import_from_file, name="import"),
]
