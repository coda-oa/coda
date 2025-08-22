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


@register.inclusion_tag("partials/breadcrumbs.html", takes_context=True)
def breadcrumbs(context: Context) -> Dict[str, Any]:
    request = context["request"]
    current_url = resolve(request.path_info)

    trail = []

    namespace = current_url.namespace
    url_name = current_url.url_name

    # Funding Requests
    if namespace == "fundingrequests" and url_name == "home":
        trail = [{"title": "Request Center"}]
    elif namespace == "fundingrequests" and url_name == "list":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests"},
        ]
    elif namespace == "fundingrequests" and url_name == "detail":
        funding_request = cast(RequestViewModel, context.get("funding_request"))
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {"title": f"Funding Request: {funding_request.request_id}"},
        ]
    elif namespace == "fundingrequests" and url_name == "review":
        funding_request = cast(RequestViewModel, context.get("fundingrequest"))
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {
                "title": f"Funding Request: {funding_request.request_id}",
                "url": f"/fundingrequests/{funding_request.id}/",
            },
            {"title": f"Review Funding Request: {funding_request.request_id}"},
        ]
    elif namespace == "fundingrequests" and url_name == "update_submitter":
        cancel_url = str(context.get("cancel_redirect_url"))
        fr_id = cancel_url.strip("/").split("/")[-1]
        fr = FundingRequestModel.objects.get(pk=fr_id)
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {
                "title": f"Funding Request: {fr.request_id}",
                "url": cancel_url,
            },
            {"title": f"Update Submitter of Funding Request: {fr.request_id}"},
        ]
    elif namespace == "fundingrequests" and url_name == "update_publication":
        cancel_url = str(context.get("cancel_redirect_url"))
        fr_id = cancel_url.strip("/").split("/")[-1]
        fr = FundingRequestModel.objects.get(pk=fr_id)
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {
                "title": f"Funding Request: {fr.request_id}",
                "url": cancel_url,
            },
            {"title": f"Update Publication Details of Funding Request: {fr.request_id}"},
        ]
    elif namespace == "fundingrequests" and url_name == "update_funding":
        cancel_url = str(context.get("cancel_redirect_url"))
        fr_id = cancel_url.strip("/").split("/")[-1]
        fr = FundingRequestModel.objects.get(pk=fr_id)
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {
                "title": f"Funding Request: {fr.request_id}",
                "url": cancel_url,
            },
            {"title": f"Update Cost and Funding of Funding Request: {fr.request_id}"},
        ]
    elif namespace == "fundingrequests" and url_name == "funders":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Organizations"},
        ]
    elif namespace == "fundingrequests" and url_name == "funders_create":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Organizations", "url": "/fundingrequests/funders/"},
            {"title": "Create Funding Organization"},
        ]
    elif namespace == "fundingrequests" and url_name == "funders_update":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Organizations", "url": "/fundingrequests/funders/"},
            {"title": "Update Funding Organization"},
        ]
    elif namespace == "fundingrequests" and url_name == "create_wizard":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {"title": "New Article"},
        ]
    elif namespace == "fundingrequests" and url_name == "create_monograph":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {"title": "New Monograph"},
        ]
    elif namespace == "fundingrequests" and url_name == "import":
        trail = [
            {"title": "Request Center", "url": "/fundingrequests/"},
            {"title": "Funding Requests", "url": "/fundingrequests/list/"},
            {"title": "Import Funding Requests"},
        ]

    # Journals & Publishers
    elif namespace == "publishing" and url_name == "home":
        trail = [{"title": "Journals & Publishers"}]
    elif namespace == "publishing:journals" and url_name == "list":
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Journals"},
        ]
    elif namespace == "publishing:journals" and url_name == "create":
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Journals", "url": "/publishing/journals/"},
            {"title": "Create Journal"},
        ]
    elif namespace == "publishing:journals" and url_name == "update":
        journal = cast(Journal, context.get("journal"))
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Journals", "url": "/publishing/journals/"},
            {"title": f"Journal: {journal.title}", "url": f"/publishing/journals/{journal.eissn}/"},
            {"title": f"Update Journal: {journal.title}"},
        ]
    elif namespace == "publishing:publishers" and url_name == "list":
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Publishers"},
        ]
    elif namespace == "publishing:journals" and url_name == "detail":
        journal = cast(Journal, context.get("journal"))
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Journals", "url": "/publishing/journals/"},
            {"title": f"Journal: {journal.title}"},
        ]
    elif namespace == "publishing:publishers" and url_name == "create":
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Publishers", "url": "/publishing/publishers/"},
            {"title": "Create Publisher"},
        ]
    elif namespace == "publishing:publishers" and url_name == "update":
        publisher = context.get("publisher")
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Publishers", "url": "/publishing/publishers/"},
            {"title": f"Update Publisher: {publisher}"},
        ]
    elif namespace == "blocklist" and url_name == "list":
        trail = [
            {"title": "Journals & Publishers", "url": "/publishing/"},
            {"title": "Blocklist"},
        ]

    # Finances
    elif namespace == "invoices" and url_name == "home":
        trail = [{"title": "Finances"}]
    elif namespace == "invoices" and url_name == "list":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Invoices"},
        ]
    elif namespace == "invoices" and url_name == "detail":
        invoice_vm = cast(InvoiceViewModel, context.get("invoice"))
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Invoices", "url": "/invoices/list/"},
            {"title": f"Invoice: {invoice_vm.number}"},
        ]
    elif namespace == "invoices" and url_name == "update":
        invoice_id = cast(InvoiceId, context.get("invoice_id"))
        invoice = repository.get_by_id(invoice_id)
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Invoices", "url": "/invoices/list/"},
            {"title": f"Invoice: {invoice.number}", "url": f"/invoices/{invoice.id}/"},
            {"title": f"Edit Invoice: {invoice.number}"},
        ]
    elif namespace == "invoices" and url_name == "import":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Invoices", "url": "/invoices/list/"},
            {"title": "Import Invoices"},
        ]
    elif namespace == "invoices" and url_name == "create":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Invoices", "url": "/invoices/list/"},
            {"title": "Create Invoice"},
        ]
    elif namespace == "invoices" and url_name == "creditor_list":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Creditors"},
        ]
    elif namespace == "invoices" and url_name == "creditor_detail":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Creditors", "url": "/invoices/creditors/"},
            {"title": f"Creditor: {context.get('creditor')}"},
        ]
    elif namespace == "invoices" and url_name == "creditor_create":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Creditors", "url": "/invoices/creditors/"},
            {"title": "Create Creditor"},
        ]
    elif namespace == "invoices" and url_name == "fundingsource_list":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Funding Sources"},
        ]
    elif namespace == "invoices" and url_name == "fundingsource_update":
        funding_source = FundingSource(context.get("fundingsource"))
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Funding Sources", "url": "/invoices/fundingsources/"},
            {"title": f"Update Funding Source: {funding_source.name}"},
        ]
    elif namespace == "invoices" and url_name == "fundingsource_create":
        trail = [
            {"title": "Finances", "url": "/invoices/"},
            {"title": "Funding Sources", "url": "/invoices/fundingsources/"},
            {"title": "Create Funding Source"},
        ]

    # Contracts
    elif namespace == "contracts" and url_name == "list":
        trail = [{"title": "Contracts"}]
    elif namespace == "contracts" and url_name == "create":
        trail = [
            {"title": "Contracts", "url": "/contracts/"},
            {"title": "Create Contract"},
        ]
    elif namespace == "contracts" and url_name == "detail":
        contract = cast(ContractModel, context.get("contract"))
        trail = [
            {"title": "Contracts", "url": "/contracts/"},
            {"title": f"Contract: {contract.name}"},
        ]
    elif namespace == "contracts" and url_name == "update":
        contract_form = cast(ContractForm, context.get("contract_form"))
        name = contract_form.data.get("name")
        url = str(context.get("url", ""))
        contract_id = url.strip("/").split("/")[-1]
        contract_url = f"/contracts/{contract_id}/"
        trail = [
            {"title": "Contracts", "url": "/contracts/"},
            {"title": f"Contract: {name}", "url": contract_url},
            {"title": f"Update Contract: {name}"},
        ]

    # Vocabularies
    elif namespace == "publications" and url_name == "vocabularies":
        trail = [{"title": "Vocabularies"}]
    elif namespace == "publications" and url_name == "vocabulary_create_limited":
        trail = [
            {"title": "Vocabularies", "url": "/publications/vocabularies/"},
            {"title": "Create Limited Vocabulary"},
        ]
    elif namespace == "publications" and url_name == "vocabulary_edit_limited":
        trail = [
            {"title": "Vocabularies", "url": "/publications/vocabularies/"},
            {"title": "Edit Limited Vocabulary"},
        ]

    # Organization
    elif namespace == "institutions" and url_name == "list":
        trail = [{"title": "Organization Structure"}]
    elif namespace == "institutions" and url_name == "create":
        trail = [
            {"title": "Organization Structure", "url": "/institutions/"},
            {"title": "Create Organization"},
        ]
    elif namespace == "institutions" and url_name == "import_view":
        trail = [
            {"title": "Organization Structure", "url": "/institutions/"},
            {"title": "Import Institutions"},
        ]
    elif namespace == "preferences" and url_name == "global_preferences":
        trail = [
            {"title": "CODA Global Preferences"},
        ]
    elif url_name == "login":
        trail = [
            {"title": "Login"},
        ]

    # home page has no breadcrumb
    elif url_name == "home":
        trail = []
    else:
        app_title = namespace.capitalize() if namespace else "App"
        page_title = url_name.replace("_", " ").capitalize() if url_name else "Page"
        trail = [
            {"title": app_title, "url": f"/{namespace}/"} if namespace else {},
            {"title": page_title},
        ]

    return {"breadcrumbs": trail}
