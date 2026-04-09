from django.urls import path

from . import views

app_name = "institutions"

urlpatterns = [
    path("", views.institution_list_view, name="list"),
    path("create/", views.create_institution_view, name="create"),
    path("<int:pk>/", views.institution_detail, name="detail"),
    path("<int:pk>/edit/", views.update_institution_view, name="edit"),
    path(
        "<int:pk>/request-set-successor/", views.request_set_successor, name="request_set_successor"
    ),
    path("<int:pk>/request-delete/", views.request_delete_institution, name="request_delete"),
    path("<int:pk>/set-successor/", views.set_successor, name="set_successor"),
    path("<int:pk>/delete/", views.delete_institution, name="delete"),
    path("<int:pk>/request-restore/", views.request_restore, name="request_restore"),
    path("<int:pk>/restore/", views.restore, name="restore"),
    path("toggle-selectable/<int:pk>", views.toggle_selectable, name="toggle_selectable"),
    path("import/", views.import_view, name="import_view"),
    path("import-file/", views.import_from_file, name="import"),
    path("export/", views.export_institutions, name="export"),
    path(
        "partial/add-institution-linkrow/",
        views.add_institution_linkrow,
        name="partial_add_linkrow",
    ),
]
