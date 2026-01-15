from django.urls import path

from .views import vocabularies


app_name = "publications"

urlpatterns = [
    path("vocabularies/", vocabularies.VocabularyListView.as_view(), name="vocabularies"),
    path(
        "vocabularies/create-limited/<int:pk>",
        vocabularies.create_limited,
        name="vocabulary_create_limited",
    ),
    path(
        "vocabularies/edit-limited/<int:pk>",
        vocabularies.edit_limited,
        name="vocabulary_edit_limited",
    ),
    path("vocabularies/delete/<int:pk>", vocabularies.delete, name="vocabulary_delete"),
    path(
        "vocabulary/request-delete/<int:pk>",
        vocabularies.request_delete,
        name="vocabulary_request_delete",
    ),
    path("vocabulary/edit/save", vocabularies.save_vocabularies, name="save_vocabularies"),
    path(
        "vocabulary/edit/move-to-forbidden",
        vocabularies.move_to_forbidden,
        name="vocabulary_move_to_forbidden",
    ),
    path(
        "vocabulary/edit/move-to-allow",
        vocabularies.move_to_allowed,
        name="vocabulary_move_to_allowed",
    ),
]
