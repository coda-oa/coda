from django.urls import path
from .views import PublisherListView, PublisherDetailView

app_name = "publishers"
urlpatterns = [
    path("", PublisherListView.as_view(), name="list"),
    path("<int:pk>/", PublisherDetailView.as_view(), name="detail"),
]
