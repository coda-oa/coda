from django.urls import path

from coda.apps.fundingrequests.forms import ContractFormset, ExternalFundingFormset
from coda.apps.fundingrequests.views import review
from coda.apps.fundingrequests.views.detailview import fundingrequest_detail
from coda.apps.fundingrequests.views.labels import LabelCreateView, attach_label, detach_label
from coda.apps.fundingrequests.views.listview import fundingrequest_list
from coda.apps.fundingrequests.views.wizard.create_article import ArticleRequestWizard
from coda.apps.fundingrequests.views.wizard.create_monograph import MonographRequestWizard
from coda.apps.fundingrequests.views.wizard.steps.publication_step import add_linkrow
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import find_publisher
from coda.apps.fundingrequests.views.wizard.update_article import (
    UpdateFundingView,
    UpdatePublicationView,
    UpdateSubmitterView,
)
from coda.apps.fundingrequests.views.wizard.update_monograph import MonographUpdateMetaView

app_name = "fundingrequests"

contract_formset = ContractFormset.get_management_view()
funding_formset = ExternalFundingFormset.get_management_view()

urlpatterns = [
    path("", fundingrequest_list, name="list"),
    path("<int:pk>/", fundingrequest_detail, name="detail"),
    path("review/<int:pk>/", review.review_page, name="review"),
    path("review/<int:pk>/submit", review.review_submit, name="review_submit"),
    path("create/wizard/", ArticleRequestWizard.as_view(), name="create_wizard"),
    path("create/monograph/", MonographRequestWizard.as_view(), name="create_monograph"),
    path(
        "update/monograph/<int:pk>/meta",
        MonographUpdateMetaView.as_view(),
        name="update_monograph_meta",
    ),
    path("update/submitter/<int:pk>/", UpdateSubmitterView.as_view(), name="update_submitter"),
    path(
        "update/publication/<int:pk>/",
        UpdatePublicationView.as_view(),
        name="update_publication",
    ),
    path("update/funding/<int:pk>/", UpdateFundingView.as_view(), name="update_funding"),
    path("create_label/<int:next>", LabelCreateView.as_view(), name="label_create"),
    path("attach_label/", attach_label, name="label_attach"),
    path("detach_label/", detach_label, name="label_detach"),
    path("partial/add-linkrow/", add_linkrow, name="partial_add_linkrow"),
    path(
        "partial/contract/",
        contract_formset.as_view(),
        name=contract_formset.name.removeprefix("fundingrequests:"),
    ),
    path(
        "partial/external-funding/",
        funding_formset.as_view(),
        name=funding_formset.name.removeprefix("fundingrequests:"),
    ),
    path("partial/search-publisher/", find_publisher, name="wizard_find_publisher"),
]
