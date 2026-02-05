from django.urls import path

from . import views

app_name = "infopage"

urlpatterns = [
    path("", views.index, name="index"),
]
