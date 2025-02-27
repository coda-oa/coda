from django.urls import path
from .views import PublisherCreateView, PublisherListView, PublisherUpdateView

app_name = "publishers"
urlpatterns = [
    path("", PublisherListView.as_view(), name="list"),
    path("create/", PublisherCreateView.as_view(), name="create"),
    path("update/<int:pk>/", PublisherUpdateView.as_view(), name="update"),
]
