import functools
from collections.abc import Callable, Sequence
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from coda.apps.contracts import repository
from coda.apps.contracts.forms import ContractForm, EntityFormset
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.apps.views import EntityListView
from coda.domain.contract import Contract, ContractId, PublisherId
from coda.domain.publication import JournalId


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
        
        return DomainQuerySet(contracts, repository.as_domain_object)


@login_required
def contract_detail(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(ContractModel, pk=pk)
    domain_contract = repository.as_domain_object(contract)
    return render(
        request,
        "contracts/contract_detail.html",
        {"contract": contract, "entity": domain_contract},
    )


@login_required
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
        contract_form = ContractForm(request.POST)
        publisher_formset = EntityFormset(request.POST, prefix="publishers")
        journal_formset = EntityFormset(request.POST, prefix="journals")
        forms: list[ContractForm | EntityFormset] = [
            contract_form,
            publisher_formset,
            journal_formset,
        ]

        if all(form.is_valid() for form in forms):
            contract_id = save_contract(contract_form, publisher_formset, journal_formset)
            return redirect("contracts:detail", contract_id)

    return render(request, "contracts/contract_create.html", context)


def create_contract(
    form: ContractForm, publisher_formset: EntityFormset, journal_formset: EntityFormset
) -> ContractId:
    publishers = cast(list[PublisherId], publisher_formset.entity_ids())
    journals = cast(list[JournalId], journal_formset.entity_ids())
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
    journals = cast(list[JournalId], journal_formset.entity_ids())

    contract.name = form.get_name()
    contract.publishers = tuple(publishers)
    contract.journals = tuple(journals)
    contract.period = form.get_period()
    contract.publication_billing = form.get_billing()
    repository.update(contract)

    return cast(ContractId, contract.id)


def get_context(
    request: HttpRequest, title: str, initial_contract: Contract | None = None
) -> dict[str, Any]:
    url = (
        reverse("contracts:create")
        if initial_contract is None
        else reverse("contracts:update", kwargs={"pk": initial_contract.id})
    )
    return {"title": title} | {"url": url} | get_forms(request, initial_contract=initial_contract)


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
