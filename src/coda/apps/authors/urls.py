from django.urls import path

from coda.apps.authors import views

app_name = "authors"

urlpatterns = [
    path("create/", views.AuthorCreateView.as_view(), name="create"),
    path("<int:pk>/", views.AuthorDetailView.as_view(), name="detail"),
]
