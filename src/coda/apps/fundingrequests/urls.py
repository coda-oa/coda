from django.urls import path

from . import views


app_name = "fundingrequests"
urlpatterns = [
    path("", views.FundingRequestListView.as_view(), name="list"),
    path("<int:pk>/", views.FundingRequestDetailView.as_view(), name="detail"),
    path("create/wizard/", views.FundingRequestWizard.as_view(), name="create_wizard"),
    path("approve/", views.approve, name="approve"),
    path("reject/", views.reject, name="reject"),
    path("open/", views.open, name="open"),
    path("create_label/<int:next>", views.LabelCreateView.as_view(), name="label_create"),
    path("attach_label/", views.attach_label, name="label_attach"),
    path("detach_label/", views.detach_label, name="label_detach"),
]
