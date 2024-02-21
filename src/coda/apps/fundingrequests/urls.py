from django.urls import path

from . import views


app_name = "fundingrequests"
urlpatterns = [
    path("", views.FundingRequestListView.as_view(), name="list"),
    path("<int:pk>/", views.FundingRequestDetailView.as_view(), name="detail"),
    path("create/", views.FundingRequestSubmitterStep.as_view(), name="create"),
    path(
        "create/publication/",
        views.FundingRequestPublicationStep.as_view(),
        name="create_publication",
    ),
]
