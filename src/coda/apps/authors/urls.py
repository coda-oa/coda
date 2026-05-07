from django.urls import path

from coda.apps.authors.forms import AuthorFormset

app_name = "authors"

author_formset_view = AuthorFormset.get_management_view()

urlpatterns = [
    path("partial/author-formset/", author_formset_view.as_view(), name="author_formset_view"),
]
