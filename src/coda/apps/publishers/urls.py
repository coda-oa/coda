from django.urls import path
from .views import (
    PublisherCreateView,
    PublisherListView,
    PublisherUpdateView,
    publisher_create_modal,
    publisher_create_modal_submit,
)

app_name = "publishers"
urlpatterns = [
    path("", PublisherListView.as_view(), name="list"),
    path("create/", PublisherCreateView.as_view(), name="create"),
    path("update/<int:pk>/", PublisherUpdateView.as_view(), name="update"),
    path("create-modal/", publisher_create_modal, name="create_modal"),
    path("create-modal/submit/", publisher_create_modal_submit, name="create_modal_submit"),
]
