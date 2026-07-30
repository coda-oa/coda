from django.urls import path

from coda.apps.fundingrequests.forms import (
    ContractFormset,
    ExternalFundingFormset,
    include_inactive_contracts,
)
from coda.apps.fundingrequests.views import review
from coda.apps.fundingrequests.views.detailview import fundingrequest_detail
from coda.apps.fundingrequests.views.doi_preview import (
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
    doi_preview_add_funding,
    doi_preview_apply_type_change,
    doi_preview_delete_funding,
    doi_preview_load_type_form,
    doi_preview_reset_funding,
    doi_preview_reset_type,
)
from coda.apps.fundingrequests.views.mass_doi_import import (
    MassDOIImportInputView,
    MassDOIImportResultView,
    MassDOIPreviewSaveView,
    MassDOIPreviewView,
)
from coda.apps.fundingrequests.views.funders import (
    add_funder_linkrow,
    archive_funder,
    delete_funder,
    fundingorganization_create_modal,
    fundingorganization_create_modal_submit,
    fundingorganizations_create,
    fundingorganizations_detail,
    fundingorganizations_list,
    fundingorganizations_update,
    request_archive_funder,
    request_delete_funder,
    request_restore_funder,
    request_update_from_ror_funder,
    restore_funder,
    update_from_ror_funder,
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
from coda.apps.fundingrequests.views.requestimport import import_fundingrequests
from coda.apps.fundingrequests.views.wizard.create_article import ArticleRequestWizard
from coda.apps.fundingrequests.views.wizard.create_monograph import MonographRequestWizard
from coda.apps.fundingrequests.views.wizard.steps.journal_step import (
    clear_journal_error,
    find_journal,
)
from coda.apps.fundingrequests.views.wizard.steps.publication_step import add_linkrow, parse_authors
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import (
    clear_publisher_error,
    find_publisher,
)
from coda.apps.fundingrequests.views.wizard.update_article import (
    UpdateExtraInformationView,
    UpdateFundingView,
    UpdatePublicationView,
)
from coda.apps.fundingrequests.views.wizard.update_monograph import MonographUpdateMetaView

app_name = "fundingrequests"

contract_formset = ContractFormset.get_management_view()
funding_formset = ExternalFundingFormset.get_management_view()

urlpatterns = [
    path("", fundingrequest_home, name="home"),
    path("list/", fundingrequest_list, name="list"),
    path("import/", import_fundingrequests, name="import"),
    path("doi-import/", DOIImportInputView.as_view(), name="doi_import_input"),
    path("doi-import/mass/", MassDOIImportInputView.as_view(), name="mass_doi_import_input"),
    path(
        "doi-import/mass-preview/<str:session_key>/",
        MassDOIPreviewView.as_view(),
        name="mass_doi_preview",
    ),
    path(
        "doi-import/mass-preview/<str:session_key>/save/",
        MassDOIPreviewSaveView.as_view(),
        name="mass_doi_preview_save",
    ),
    path(
        "doi-import/mass-result/<str:result_key>/",
        MassDOIImportResultView.as_view(),
        name="mass_doi_result",
    ),
    path(
        "doi-preview/<str:session_key>/", DOIPreviewDetailView.as_view(), name="doi_preview_detail"
    ),
    path(
        "doi-preview/<str:session_key>/delete-funding",
        doi_preview_delete_funding,
        name="doi_preview_delete_funding",
    ),
    path(
        "doi-preview/<str:session_key>/add-funding",
        doi_preview_add_funding,
        name="doi_preview_add_funding",
    ),
    path(
        "doi-preview/<str:session_key>/reset-funding",
        doi_preview_reset_funding,
        name="doi_preview_reset_funding",
    ),
    path(
        "doi-preview/<str:session_key>/save/", DOIPreviewSaveView.as_view(), name="doi_preview_save"
    ),
    path(
        "doi-preview/<str:session_key>/load-type-form/",
        doi_preview_load_type_form,
        name="doi_preview_load_type_form",
    ),
    path(
        "doi-preview/<str:session_key>/apply-type-change/",
        doi_preview_apply_type_change,
        name="doi_preview_apply_type_change",
    ),
    path(
        "doi-preview/<str:session_key>/reset-type/",
        doi_preview_reset_type,
        name="doi_preview_reset_type",
    ),
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
    path("funders/<int:pk>/", fundingorganizations_detail, name="funder_detail"),
    path("funders/create/", fundingorganizations_create, name="funders_create"),
    path("funders/create-modal/", fundingorganization_create_modal, name="funders_create_modal"),
    path(
        "funders/create-modal/submit/",
        fundingorganization_create_modal_submit,
        name="funders_create_modal_submit",
    ),
    path("funders/update/<int:pk>/", fundingorganizations_update, name="funders_update"),
    path(
        "funders/<int:pk>/request-archive/", request_archive_funder, name="funder_request_archive"
    ),
    path("funders/<int:pk>/archive/", archive_funder, name="funder_archive"),
    path("funders/<int:pk>/request-delete/", request_delete_funder, name="funder_request_delete"),
    path("funders/<int:pk>/delete/", delete_funder, name="funder_delete"),
    path(
        "funders/<int:pk>/request-restore/", request_restore_funder, name="funder_request_restore"
    ),
    path("funders/<int:pk>/restore/", restore_funder, name="funder_restore"),
    path(
        "funders/<int:pk>/request-update-from-ror/",
        request_update_from_ror_funder,
        name="funder_request_update_from_ror",
    ),
    path(
        "funders/<int:pk>/update-from-ror/",
        update_from_ror_funder,
        name="funder_update_from_ror",
    ),
    path(
        "funders/partial/add-linkrow/",
        add_funder_linkrow,
        name="funders_partial_add_linkrow",
    ),
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
    path("partial/search-journal/", find_journal, name="wizard_find_journal"),
    path("contract/inactive", include_inactive_contracts, name="include_inactive_contracts"),
    path("clear-journal-error/", clear_journal_error, name="clear_journal_error"),
    path("clear-publisher-error/", clear_publisher_error, name="clear_publisher_error"),
]
