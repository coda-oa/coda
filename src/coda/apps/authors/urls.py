from django.urls import path

from coda.apps.authors import views
from coda.apps.authors.forms import AuthorFormset

app_name = "authors"

author_formset_view = AuthorFormset.get_management_view()

urlpatterns = [
    path("create/", views.AuthorCreateView.as_view(), name="create"),
    path("<int:pk>/", views.AuthorDetailView.as_view(), name="detail"),
    path("partial/author-formset/", author_formset_view.as_view(), name="author_formset_view"),
]
