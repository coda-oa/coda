import functools
from collections.abc import Callable
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from coda.apps.contracts import services
from coda.apps.contracts.forms import ContractForm, EntityFormset
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.apps.views import EntityListView
from coda.contract import Contract, ContractId, PublisherId
from coda.publication import JournalId


class ContractListView(LoginRequiredMixin, EntityListView[Contract]):
    entity_name = "Contracts"
    entity_create_url = "contracts:create"
    entity_list_item_template = "contracts/contract_list_item.html"
    entity_list_layout_classes = "grid-container"

    def get_entities(self, request: HttpRequest) -> list[Contract]:
        return services.all()


@login_required
def contract_detail(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(ContractModel, pk=pk)
    return render(request, "contracts/contract_detail.html", {"contract": contract})


@login_required
def edit_contract_view(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    save_contract: Callable[[ContractForm, EntityFormset, EntityFormset], ContractId]
    if pk is not None:
        contract = services.get_by_id(ContractId(pk))
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
    contract = Contract.new(form.get_name(), publishers, form.get_period(), journals)
    return services.save(contract)


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
    return services.save(contract)


def get_context(
    request: HttpRequest, title: str, initial_contract: Contract | None = None
) -> dict[str, Any]:
    return {"title": title} | get_forms(request, initial_contract=initial_contract)


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
            [{"id": publisher.id, "name": publisher.name} for publisher in publishers],
            prefix="publishers",
            form_id="publishers-formset",
        )

        journals = Journal.objects.filter(pk__in=initial_contract.journals)
        journal_formset = EntityFormset.from_data(
            [{"id": journal.id, "name": journal.title} for journal in journals],
            prefix="journals",
            form_id="journals-formset",
        )
    else:
        contract_form = ContractForm()
        publisher_formset = EntityFormset(prefix="publishers", form_id="publishers-formset")
        journal_formset = EntityFormset(prefix="journals", form_id="journals")

    return {
        "contract_form": contract_form,
        "publisher_formset": publisher_formset,
        "journal_formset": journal_formset,
    }
