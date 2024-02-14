from django.urls import path

from . import views


app_name = "fundingrequests"
urlpatterns = [
    path("", views.FundingRequestListView.as_view(), name="list"),
    path("<int:pk>/", views.FundingRequestDetailView.as_view(), name="detail"),
]
