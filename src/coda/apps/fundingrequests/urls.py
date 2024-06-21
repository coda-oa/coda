from django.urls import path

from coda.apps.fundingrequests.views.detailview import fundingrequest_detail
from coda.apps.fundingrequests.views.labels import LabelCreateView, attach_label, detach_label
from coda.apps.fundingrequests.views.listview import fundingrequest_list
from coda.apps.fundingrequests.views import review
from coda.apps.fundingrequests.views.wizard.create import FundingRequestWizard
from coda.apps.fundingrequests.views.wizard.partials import add_linkrow
from coda.apps.fundingrequests.views.wizard.update import (
    UpdateFundingView,
    UpdatePublicationView,
    UpdateSubmitterView,
)

app_name = "fundingrequests"
urlpatterns = [
    path("", fundingrequest_list, name="list"),
    path("<int:pk>/", fundingrequest_detail, name="detail"),
    path("create/wizard/", FundingRequestWizard.as_view(), name="create_wizard"),
    path("update/submitter/<int:pk>/", UpdateSubmitterView.as_view(), name="update_submitter"),
    path(
        "update/publication/<int:pk>/",
        UpdatePublicationView.as_view(),
        name="update_publication",
    ),
    path("update/funding/<int:pk>/", UpdateFundingView.as_view(), name="update_funding"),
    path("approve/", review.approve, name="approve"),
    path("reject/", review.reject, name="reject"),
    path("open/", review.open, name="open"),
    path("create_label/<int:next>", LabelCreateView.as_view(), name="label_create"),
    path("attach_label/", attach_label, name="label_attach"),
    path("detach_label/", detach_label, name="label_detach"),
    path("partial/add-linkrow/", add_linkrow, name="partial_add_linkrow"),
]
