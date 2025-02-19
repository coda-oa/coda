from django.urls import path

from coda.apps.fundingrequests.forms import ContractFormset, ExternalFundingFormset
from coda.apps.fundingrequests.views import review
from coda.apps.fundingrequests.views.detailview import fundingrequest_detail
from coda.apps.fundingrequests.views.funders import (
    fundingorganizations_create,
    fundingorganizations_delete,
    fundingorganizations_list,
    fundingorganizations_update,
)
from coda.apps.fundingrequests.views.home import fundingrequest_home
from coda.apps.fundingrequests.views.labels import (
    attach_label,
    detach_label,
    label_create_view,
    label_delete_view,
    label_list_view,
    label_update_view,
)
from coda.apps.fundingrequests.views.listview import fundingrequest_list
from coda.apps.fundingrequests.views.wizard.create_article import ArticleRequestWizard
from coda.apps.fundingrequests.views.wizard.create_monograph import MonographRequestWizard
from coda.apps.fundingrequests.views.wizard.steps.publication_step import add_linkrow, parse_authors
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import find_publisher
from coda.apps.fundingrequests.views.wizard.update_article import (
    UpdateFundingView,
    UpdatePublicationView,
    UpdateExtraInformationView,
)
from coda.apps.fundingrequests.views.wizard.update_monograph import MonographUpdateMetaView

app_name = "fundingrequests"

contract_formset = ContractFormset.get_management_view()
funding_formset = ExternalFundingFormset.get_management_view()

urlpatterns = [
    path("", fundingrequest_home, name="home"),
    path("list/", fundingrequest_list, name="list"),
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
    path(
        "update/submitter/<int:pk>/", UpdateExtraInformationView.as_view(), name="update_submitter"
    ),
    path(
        "update/publication/<int:pk>/",
        UpdatePublicationView.as_view(),
        name="update_publication",
    ),
    path("update/funding/<int:pk>/", UpdateFundingView.as_view(), name="update_funding"),
    path("labels/", label_list_view, name="label_list"),
    path("labels/create/", label_create_view, name="label_create"),
    path("labels/create/<int:next>/", label_create_view, name="label_create"),
    path("labels/update/<int:pk>/", label_update_view, name="label_update"),
    path("labels/delete/<int:pk>/", label_delete_view, name="label_delete"),
    path("labels/attach/", attach_label, name="label_attach"),
    path("labels/detach", detach_label, name="label_detach"),
    path("funders/", fundingorganizations_list, name="funders"),
    path("funders/create/", fundingorganizations_create, name="funders_create"),
    path("funders/update/<int:pk>/", fundingorganizations_update, name="funders_update"),
    path("funders/delete/<int:pk>/", fundingorganizations_delete, name="funders_delete"),
    path("partial/add-linkrow/", add_linkrow, name="partial_add_linkrow"),
    path("partial/parse-authors/", parse_authors, name="parse_authors"),
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
