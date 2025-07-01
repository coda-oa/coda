from django.urls import include, path

from coda.apps.publishing import views

app_name = "publishing"
urlpatterns = [
    path("", views.publishing_home, name="home"),
    path("publishers/", include("coda.apps.publishers.urls", namespace="publishers")),
    path("journals/", include("coda.apps.journals.urls", namespace="journals")),
]
