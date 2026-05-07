import functools
from collections.abc import Callable, Sequence
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts import repository
from coda.apps.contracts.mappers import ContractDomainMapper
from coda.apps.contracts.forms import ContractForm, ContractLinkForm, EntityFormset
from coda.apps.contracts.models import Contract as ContractModel, ContractLink, ContractLinkType
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.apps.views import EntityListView
from coda.domain.contract import Contract, ContractId, PublisherId
from coda.domain.publication import JournalId


@breadcrumb("Contracts")
class ContractListView(LoginRequiredMixin, EntityListView[Contract]):
    entity_name = "Contracts"
    entity_create_url = "contracts:create"
    entity_list_item_template = "contracts/contract_list_item.html"
    entity_filter_template = "entity_generic_filter.html"
    use_generic_entity_filter = True

    def get_entities(self, request: HttpRequest) -> Sequence[Contract]:
        search_term = request.GET.get("query", "").strip()
        contracts = ContractModel.objects.all()
        if search_term:
            contracts = contracts.filter(name__icontains=search_term)

        return DomainQuerySet(ContractDomainMapper.prefetch(contracts), ContractDomainMapper.map)


@login_required
@breadcrumb("Contract Detail", parent_url_name="contracts:list", preserve_filters=True)
def contract_detail(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(ContractModel, pk=pk)
    domain_contract = ContractDomainMapper.map(contract)
    return render(
        request,
        "contracts/contract_detail.html",
        {"contract": contract, "entity": domain_contract},
    )


@login_required
@breadcrumb(
    title=lambda request, *args, **kwargs: (
        "Update Contract" if kwargs.get("pk") else "Create Contract"
    ),
    parent_url_name=lambda request, *args, **kwargs: (
        "contracts:detail" if kwargs.get("pk") else "contracts:list"
    ),
)
def edit_contract_view(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    save_contract: Callable[[ContractForm, EntityFormset, EntityFormset], ContractId]
    if pk is not None:
        contract = repository.get_by_id(ContractId(pk))
        context = get_context(request, "Update Contract", initial_contract=contract)
        save_contract = functools.partial(update_contract, contract)
    else:
        context = get_context(request, "Create Contract")
        save_contract = create_contract

    if request.method == "POST":
        response = _handle_contract_post(request, save_contract, context)
        if response:
            return response

    return render(request, "contracts/contract_create.html", context)


def _handle_contract_post(
    request: HttpRequest,
    save_contract: Callable[[ContractForm, EntityFormset, EntityFormset], ContractId],
    context: dict[str, Any],
) -> HttpResponse | None:
    contract_form = ContractForm(request.POST)
    publisher_formset = EntityFormset(request.POST, prefix="publishers")
    journal_formset = EntityFormset(request.POST, prefix="journals")
    forms: list[ContractForm | EntityFormset] = [
        contract_form,
        publisher_formset,
        journal_formset,
    ]

    link_forms = get_link_forms(request)
    links_valid = all(link_form.is_valid() for link_form in link_forms)

    if all(form.is_valid() for form in forms) and links_valid:
        contract_id = save_contract(contract_form, publisher_formset, journal_formset)
        _save_contract_links(contract_id, link_forms)
        return redirect("contracts:detail", contract_id)

    context["links"] = get_links_with_errors(request)
    return None


def _save_contract_links(contract_id: ContractId, link_forms: list[ContractLinkForm]) -> None:
    contract_model = ContractModel.objects.get(pk=contract_id.pk)
    ContractLink.objects.filter(contract=contract_model).delete()

    for link_form in link_forms:
        link_data = link_form.get_form_data()
        if link_data["link_type"] and link_data["link_value"]:
            link_type = ContractLinkType.objects.get(name=link_data["link_type"])
            ContractLink.objects.create(
                contract=contract_model,
                type=link_type,
                value=link_data["link_value"],
            )


def create_contract(
    form: ContractForm, publisher_formset: EntityFormset, journal_formset: EntityFormset
) -> ContractId:
    publishers = cast(list[PublisherId], publisher_formset.entity_ids())
    journals = [JournalId(j) for j in journal_formset.entity_ids()]
    contract = Contract.new(
        form.get_name(), publishers, form.get_period(), journals, form.get_billing()
    )
    return repository.create(contract)


def update_contract(
    contract: Contract,
    form: ContractForm,
    publisher_formset: EntityFormset,
    journal_formset: EntityFormset,
) -> ContractId:
    publishers = cast(list[PublisherId], publisher_formset.entity_ids())
    journals = [JournalId(j) for j in journal_formset.entity_ids()]

    contract.name = form.get_name()
    contract.publishers = tuple(publishers)
    contract.journals = tuple(journals)
    contract.period = form.get_period()
    contract.publication_billing = form.get_billing()
    repository.update(contract)

    return contract.id


def get_context(
    request: HttpRequest, title: str, initial_contract: Contract | None = None
) -> dict[str, Any]:
    url = (
        reverse("contracts:create")
        if initial_contract is None
        else reverse("contracts:update", kwargs={"pk": initial_contract.id})
    )

    contract_model = None
    if initial_contract is not None and initial_contract.id is not None:
        contract_model = ContractModel.objects.get(pk=initial_contract.id.pk)

    links_data = get_existing_links(contract_model) if contract_model else []

    return (
        {"title": title}
        | {"url": url}
        | {"link_types": ContractLinkType.objects.all()}
        | {"contract": contract_model}
        | {"links": links_data}
        | get_forms(request, initial_contract=initial_contract)
    )


def get_forms(request: HttpRequest, initial_contract: Contract | None = None) -> dict[str, Any]:
    if request.method == "POST":
        contract_form = ContractForm(request.POST)
        publisher_formset = EntityFormset(
            request.POST, form_id="publishers-formset", prefix="publishers"
        )
        journal_formset = EntityFormset(request.POST, form_id="journals-formset", prefix="journals")
    elif initial_contract is not None:
        contract_form = ContractForm.from_contract(initial_contract)

        publishers = Publisher.objects.filter(pk__in=initial_contract.publishers)
        publisher_formset = EntityFormset.from_data(
            [{"entity_id": publisher.pk, "name": publisher.name} for publisher in publishers],
            prefix="publishers",
            form_id="publishers-formset",
        )

        journals = Journal.objects.filter(pk__in=initial_contract.journals)
        journal_formset = EntityFormset.from_data(
            [{"entity_id": journal.pk, "name": journal.title} for journal in journals],
            prefix="journals",
            form_id="journals-formset",
        )
    else:
        contract_form = ContractForm()
        publisher_formset = EntityFormset(prefix="publishers", form_id="publishers-formset")
        journal_formset = EntityFormset(prefix="journals", form_id="journals-formset")

    return {
        "contract_form": contract_form,
        "publisher_formset": publisher_formset,
        "journal_formset": journal_formset,
    }


def get_link_forms(request: HttpRequest) -> list[ContractLinkForm]:
    types = request.POST.getlist("link_type")
    values = request.POST.getlist("link_value")
    return [
        ContractLinkForm({"link_type": link_type, "link_value": link_value})
        for link_type, link_value in zip(types, values)
    ]


def get_links_with_errors(request: HttpRequest) -> list[dict[str, Any]]:
    forms = get_link_forms(request)
    for form in forms:
        form.full_clean()
    return [{"link": form.get_form_data(), "errors": form.errors} for form in forms]


def get_existing_links(contract_model: ContractModel | None) -> list[dict[str, Any]]:
    if not contract_model:
        return []
    return [
        {"link": {"link_type": link.type.name, "link_value": link.value}, "errors": {}}
        for link in contract_model.links.all()
    ]


@login_required
@require_POST
def add_contract_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "partials/linkrow.html",
        {"link_types": ContractLinkType.objects.all()},
    )
