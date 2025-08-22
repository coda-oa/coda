from django import template
from django.template import Context
from django.urls import resolve
from typing import Dict, Any, cast

from coda.apps.contracts.forms import ContractForm
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.fundingrequests.views.detailview import RequestViewModel
from coda.apps.invoices.models import FundingSource
from coda.apps.invoices.views.inspect import InvoiceViewModel
from coda.apps.journals.models import Journal
from coda.domain.invoice import InvoiceId
from coda.apps.invoices import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel

register = template.Library()

# === Request Center ===
REQUEST_CENTER_TITLE = {"title": "Request Center"}
REQUEST_CENTER_URL = {"title": "Request Center", "url": "/fundingrequests/"}

FR_LIST_TITLE = {"title": "Funding Requests"}
FR_LIST_URL = {"title": "Funding Requests", "url": "/fundingrequests/list/"}

FR_FUNDERS_TITLE = {"title": "Funding Organizations"}
FR_FUNDERS_URL = {"title": "Funding Organizations", "url": "/fundingrequests/funders/"}
FR_FUNDERS_CREATE_TITLE = {"title": "Create Funding Organization"}
FR_FUNDERS_UPDATE_TITLE = {"title": "Update Funding Organization"}
FR_FUNDERS_NEW_ARTICLE_TITLE = {"title": "New Article"}
FR_FUNDERS_NEW_MONOGRAPH_TITLE = {"title": "New Monograph"}
FR_IMPORT_TITLE = {"title": "Import Funding Requests"}

# === Journals & Publishers ===
JOURNALS_TITLE = {"title": "Journals & Publishers"}
JOURNALS_URL = {"title": "Journals & Publishers", "url": "/publishing/"}
JOURNALS_JOURNAL_TITLE = {"title": "Journals"}
JOURNALS_JOURNAL_URL = {"title": "Journals", "url": "/publishing/journals/"}
JOURNALS_JOURNAL_CREATE_TITLE = {"title": "Create Journal"}
JOURNALS_PUBLISHERS_URL = {"title": "Publishers", "url": "/publishing/publishers/"}

# === Finances ===
FINANCES_URL: dict[str, str] = {"title": "Finances", "url": "/invoices/"}
INVOICES_URL: dict[str, str] = {"title": "Invoices", "url": "/invoices/list/"}
CREDITORS_URL: dict[str, str] = {"title": "Creditors", "url": "/invoices/creditors/"}
FUNDING_SOURCES_URL: dict[str, str] = {
    "title": "Funding Sources",
    "url": "/invoices/fundingsources/",
}
# === Contracts ===
CONTRACTS_URL: dict[str, str] = {"title": "Contracts", "url": "/contracts/"}

# === Vocabularies ===
VOCABULARIES_URL: dict[str, str] = {"title": "Vocabularies", "url": "/publications/vocabularies/"}

# === Organization ===
ORG_STRUCT_URL: dict[str, str] = {"title": "Organization Structure", "url": "/institutions/"}


# === Request Center ===
def breadcrumb_funding_request_home(context: Context) -> list[dict[str, str]]:
    return [REQUEST_CENTER_TITLE.copy()]


def breadcrumb_funding_request_list(context: Context) -> list[dict[str, str]]:
    return [REQUEST_CENTER_URL.copy(), FR_LIST_URL.copy()]


def breadcrumb_funding_request_detail(context: Context) -> list[dict[str, str]]:
    funding_request = cast(RequestViewModel, context.get("funding_request"))
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        {"title": f"Funding Request: {funding_request.request_id}"},
    ]


def breadcrumb_funding_request_review(context: Context) -> list[dict[str, str]]:
    funding_request = cast(RequestViewModel, context.get("fundingrequest"))
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        {
            "title": f"Funding Request: {funding_request.request_id}",
            "url": f"/fundingrequests/{funding_request.id}/",
        },
        {"title": f"Review Funding Request: {funding_request.request_id}"},
    ]


def breadcrumb_funding_request_update_submitter(context: Context) -> list[dict[str, str]]:
    cancel_url = str(context.get("cancel_redirect_url"))
    fr_id = cancel_url.strip("/").split("/")[-1]
    fr = FundingRequestModel.objects.get(pk=fr_id)
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        {
            "title": f"Funding Request: {fr.request_id}",
            "url": cancel_url,
        },
        {"title": f"Update Submitter of Funding Request: {fr.request_id}"},
    ]


def breadcrumb_funding_request_update_publication(context: Context) -> list[dict[str, str]]:
    cancel_url = str(context.get("cancel_redirect_url"))
    fr_id = cancel_url.strip("/").split("/")[-1]
    fr = FundingRequestModel.objects.get(pk=fr_id)
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        {
            "title": f"Funding Request: {fr.request_id}",
            "url": cancel_url,
        },
        {"title": f"Update Publication Details of Funding Request: {fr.request_id}"},
    ]


def breadcrumb_funding_request_update_funding(context: Context) -> list[dict[str, str]]:
    cancel_url = str(context.get("cancel_redirect_url"))
    fr_id = cancel_url.strip("/").split("/")[-1]
    fr = FundingRequestModel.objects.get(pk=fr_id)
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        {
            "title": f"Funding Request: {fr.request_id}",
            "url": cancel_url,
        },
        {"title": f"Update Cost and Funding of Funding Request: {fr.request_id}"},
    ]


def breadcrumb_funding_request_funders(context: Context) -> list[dict[str, str]]:
    return [
        REQUEST_CENTER_URL.copy(),
        FR_FUNDERS_TITLE.copy(),
    ]


def breadcrumb_funding_request_funders_create(context: Context) -> list[dict[str, str]]:
    return [
        REQUEST_CENTER_URL.copy(),
        FR_FUNDERS_URL.copy(),
        FR_FUNDERS_CREATE_TITLE.copy(),
    ]


def breadcrumb_funding_request_funders_update(context: Context) -> list[dict[str, str]]:
    return [
        REQUEST_CENTER_URL.copy(),
        FR_FUNDERS_URL.copy(),
        FR_FUNDERS_UPDATE_TITLE.copy(),
    ]


def breadcrumb_funding_request_create_wizard(context: Context) -> list[dict[str, str]]:
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        FR_FUNDERS_NEW_ARTICLE_TITLE.copy(),
    ]


def breadcrumb_funding_request_create_monograph(context: Context) -> list[dict[str, str]]:
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        FR_FUNDERS_NEW_MONOGRAPH_TITLE.copy(),
    ]


def breadcrumb_funding_request_import(context: Context) -> list[dict[str, str]]:
    return [
        REQUEST_CENTER_URL.copy(),
        FR_LIST_URL.copy(),
        FR_IMPORT_TITLE.copy(),
    ]


# === Journals & Publishers ===
def breadcrumb_publishing_home(context: Context) -> list[dict[str, str]]:
    return [JOURNALS_TITLE]


def breadcrumb_publishing_journals_list(context: Context) -> list[dict[str, str]]:
    return [
        JOURNALS_URL.copy(),
        JOURNALS_JOURNAL_TITLE.copy(),
    ]


def breadcrumb_publishing_journals_create(context: Context) -> list[dict[str, str]]:
    return [
        JOURNALS_URL.copy(),
        JOURNALS_JOURNAL_URL.copy(),
        JOURNALS_JOURNAL_CREATE_TITLE.copy(),
    ]


def breadcrumb_publishing_journals_update(context: Context) -> list[dict[str, str]]:
    journal = cast(Journal, context.get("journal"))
    return [
        JOURNALS_URL.copy(),
        JOURNALS_JOURNAL_URL.copy(),
        {"title": f"Journal: {journal.title}", "url": f"/publishing/journals/{journal.eissn}/"},
        {"title": f"Update Journal: {journal.title}"},
    ]


def breadcrumb_publishing_publishers_list(context: Context) -> list[dict[str, str]]:
    return [
        JOURNALS_URL.copy(),
        {"title": "Publishers"},
    ]


def breadcrumb_publishing_publishers_create(context: Context) -> list[dict[str, str]]:
    return [
        JOURNALS_URL.copy(),
        JOURNALS_PUBLISHERS_URL.copy(),
        {"title": "Create Publisher"},
    ]


def breadcrumb_publishing_journals_detail(context: Context) -> list[dict[str, str]]:
    journal = cast(Journal, context.get("journal"))
    return [
        JOURNALS_URL.copy(),
        JOURNALS_JOURNAL_URL.copy(),
        {"title": f"Journal: {journal.title}"},
    ]


def breadcrumb_publishing_publishers_update(context: Context) -> list[dict[str, str]]:
    publisher = context.get("publisher")
    return [
        JOURNALS_URL.copy(),
        JOURNALS_PUBLISHERS_URL.copy(),
        {"title": f"Update Publisher: {publisher}"},
    ]


def breadcrumb_blocklist_list(context: Context) -> list[dict[str, str]]:
    return [
        JOURNALS_URL.copy(),
        {"title": "Blocklist"},
    ]


# === Finances ===
def breadcrumb_invoices_home(context: Context) -> list[dict[str, str]]:
    return [{"title": "Finances"}]


def breadcrumb_invoices_list(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        {"title": "Invoices"},
    ]


def breadcrumb_invoices_detail(context: Context) -> list[dict[str, str]]:
    invoice_vm = cast(InvoiceViewModel, context.get("invoice"))
    return [
        FINANCES_URL.copy(),
        INVOICES_URL.copy(),
        {"title": f"Invoice: {invoice_vm.number}"},
    ]


def breadcrumb_invoices_update(context: Context) -> list[dict[str, str]]:
    invoice_id = cast(InvoiceId, context.get("invoice_id"))
    invoice = repository.get_by_id(invoice_id)
    return [
        FINANCES_URL.copy(),
        INVOICES_URL.copy(),
        {"title": f"Invoice: {invoice.number}", "url": f"/invoices/{invoice.id}/"},
        {"title": f"Edit Invoice: {invoice.number}"},
    ]


def breadcrumb_invoices_import(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        INVOICES_URL.copy(),
        {"title": "Import Invoices"},
    ]


def breadcrumb_invoices_create(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        INVOICES_URL.copy(),
        {"title": "Create Invoice"},
    ]


def breadcrumb_creditor_list(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        {"title": "Creditors"},
    ]


def breadcrumb_creditor_detail(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        CREDITORS_URL.copy(),
        {"title": f"Creditor: {context.get('creditor')}"},
    ]


def breadcrumb_creditor_create(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        CREDITORS_URL.copy(),
        {"title": "Create Creditor"},
    ]


def breadcrumb_fundingsource_list(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        {"title": "Funding Sources"},
    ]


def breadcrumb_fundingsource_update(context: Context) -> list[dict[str, str]]:
    request = context["request"]
    pk = request.resolver_match.kwargs.get("pk")
    funding_source = FundingSource.objects.get(id=pk)
    return [
        FINANCES_URL.copy(),
        FUNDING_SOURCES_URL.copy(),
        {"title": f"Update Funding Source: {funding_source.name}"},
    ]


def breadcrumb_fundingsource_create(context: Context) -> list[dict[str, str]]:
    return [
        FINANCES_URL.copy(),
        FUNDING_SOURCES_URL.copy(),
        {"title": "Create Funding Source"},
    ]


# === Contracts ===
def breadcrumb_contracts_list(context: Context) -> list[dict[str, str]]:
    return [{"title": "Contracts"}]


def breadcrumb_contracts_create(context: Context) -> list[dict[str, str]]:
    return [
        CONTRACTS_URL.copy(),
        {"title": "Create Contract"},
    ]


def breadcrumb_contracts_detail(context: Context) -> list[dict[str, str]]:
    contract = cast(ContractModel, context.get("contract"))
    return [
        CONTRACTS_URL.copy(),
        {"title": f"Contract: {contract.name}"},
    ]


def breadcrumb_contracts_update(context: Context) -> list[dict[str, str]]:
    contract_form = cast(ContractForm, context.get("contract_form"))
    name = contract_form.data.get("name")
    url = str(context.get("url", ""))
    contract_id = url.strip("/").split("/")[-1]
    contract_url = f"/contracts/{contract_id}/"
    return [
        CONTRACTS_URL.copy(),
        {"title": f"Contract: {name}", "url": contract_url},
        {"title": f"Update Contract: {name}"},
    ]


# === Vocabularies ===
def breadcrumb_vocabularies(context: Context) -> list[dict[str, str]]:
    return [{"title": "Vocabularies"}]


def breadcrumb_vocabularies_create_limited(context: Context) -> list[dict[str, str]]:
    return [
        VOCABULARIES_URL.copy(),
        {"title": "Create Limited Vocabulary"},
    ]


def breadcrumb_vocabularies_edit_limited(context: Context) -> list[dict[str, str]]:
    return [
        VOCABULARIES_URL.copy(),
        {"title": "Edit Limited Vocabulary"},
    ]


# === Organization ===
def breadcrumb_org_list(context: Context) -> list[dict[str, str]]:
    return [{"title": "Organization Structure"}]


def breadcrumb_org_create(context: Context) -> list[dict[str, str]]:
    return [
        ORG_STRUCT_URL.copy(),
        {"title": "Create Organization"},
    ]


def breadcrumb_org_import(context: Context) -> list[dict[str, str]]:
    return [
        ORG_STRUCT_URL.copy(),
        {"title": "Import Institutions"},
    ]


# === Preferences / Login ===
def breadcrumb_global_preferences(context: Context) -> list[dict[str, str]]:
    return [{"title": "CODA Global Preferences"}]


def breadcrumb_login(context: Context) -> list[dict[str, str]]:
    return [{"title": "Login"}]


def breadcrumb_home(context: Context) -> list[dict[str, str]]:
    return []


PUBLISHING_JOURNALS_NAMESPACE = "publishing:journals"
PUBLISHING_PUBLISHERS_NAMESPACE = "publishing:publishers"

BREADCRUMB_MAP = {
    ("fundingrequests", "home"): breadcrumb_funding_request_home,
    ("fundingrequests", "list"): breadcrumb_funding_request_list,
    ("fundingrequests", "detail"): breadcrumb_funding_request_detail,
    ("fundingrequests", "review"): breadcrumb_funding_request_review,
    ("fundingrequests", "update_submitter"): breadcrumb_funding_request_update_submitter,
    ("fundingrequests", "update_publication"): breadcrumb_funding_request_update_publication,
    ("fundingrequests", "update_funding"): breadcrumb_funding_request_update_funding,
    ("fundingrequests", "funders"): breadcrumb_funding_request_funders,
    ("fundingrequests", "funders_create"): breadcrumb_funding_request_funders_create,
    ("fundingrequests", "funders_update"): breadcrumb_funding_request_funders_update,
    ("fundingrequests", "create_wizard"): breadcrumb_funding_request_create_wizard,
    ("fundingrequests", "create_monograph"): breadcrumb_funding_request_create_monograph,
    ("fundingrequests", "import"): breadcrumb_funding_request_import,
    ("publishing", "home"): breadcrumb_publishing_home,
    (PUBLISHING_JOURNALS_NAMESPACE, "list"): breadcrumb_publishing_journals_list,
    (PUBLISHING_JOURNALS_NAMESPACE, "create"): breadcrumb_publishing_journals_create,
    (PUBLISHING_JOURNALS_NAMESPACE, "update"): breadcrumb_publishing_journals_update,
    (PUBLISHING_JOURNALS_NAMESPACE, "detail"): breadcrumb_publishing_journals_detail,
    (PUBLISHING_PUBLISHERS_NAMESPACE, "list"): breadcrumb_publishing_publishers_list,
    (PUBLISHING_PUBLISHERS_NAMESPACE, "update"): breadcrumb_publishing_publishers_update,
    (PUBLISHING_PUBLISHERS_NAMESPACE, "create"): breadcrumb_publishing_publishers_create,
    ("blocklist", "list"): breadcrumb_blocklist_list,
    ("invoices", "home"): breadcrumb_invoices_home,
    ("invoices", "list"): breadcrumb_invoices_list,
    ("invoices", "detail"): breadcrumb_invoices_detail,
    ("invoices", "update"): breadcrumb_invoices_update,
    ("invoices", "import"): breadcrumb_invoices_import,
    ("invoices", "create"): breadcrumb_invoices_create,
    ("invoices", "creditor_list"): breadcrumb_creditor_list,
    ("invoices", "creditor_detail"): breadcrumb_creditor_detail,
    ("invoices", "creditor_create"): breadcrumb_creditor_create,
    ("invoices", "fundingsource_list"): breadcrumb_fundingsource_list,
    ("invoices", "fundingsource_update"): breadcrumb_fundingsource_update,
    ("invoices", "fundingsource_create"): breadcrumb_fundingsource_create,
    ("contracts", "list"): breadcrumb_contracts_list,
    ("contracts", "create"): breadcrumb_contracts_create,
    ("contracts", "detail"): breadcrumb_contracts_detail,
    ("contracts", "update"): breadcrumb_contracts_update,
    ("publications", "vocabularies"): breadcrumb_vocabularies,
    ("publications", "vocabulary_create_limited"): breadcrumb_vocabularies_create_limited,
    ("publications", "vocabulary_edit_limited"): breadcrumb_vocabularies_edit_limited,
    ("institutions", "list"): breadcrumb_org_list,
    ("institutions", "create"): breadcrumb_org_create,
    ("institutions", "import_view"): breadcrumb_org_import,
    ("preferences", "global_preferences"): breadcrumb_global_preferences,
    ("", "login"): breadcrumb_login,
    ("", "home"): breadcrumb_home,
}


@register.inclusion_tag("partials/breadcrumbs.html", takes_context=True)
def breadcrumbs(context: Context) -> Dict[str, Any]:
    request = context["request"]
    current_url = resolve(request.path_info)

    trail = []

    namespace = current_url.namespace
    url_name = current_url.url_name

    trail_func = None
    if namespace is not None and url_name is not None:
        trail_func = BREADCRUMB_MAP.get((namespace, url_name))

    if trail_func:
        trail = trail_func(context)
    else:
        app_title = namespace.capitalize() if namespace else "App"
        page_title = url_name.replace("_", " ").capitalize() if url_name else "Page"
        trail = [
            {"title": app_title, "url": f"/{namespace}/"} if namespace else {},
            {"title": page_title},
        ]

    return {"breadcrumbs": trail}
