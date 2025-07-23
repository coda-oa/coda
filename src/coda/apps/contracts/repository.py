from collections.abc import Iterable, Sequence

from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.domainqueryset import DomainQuerySet
from coda.domain.contract import Contract, ContractId, PublicationBilling, PublisherId
from coda.domain.date import DateRange
from coda.domain.publication import JournalId
from coda.domain.string import NonEmptyStr
from coda.lazyiterable import LazyCachedIterable
from django.db import models


def first() -> Contract | None:
    c = ContractModel.objects.first()
    if not c:
        return None

    return as_domain_object(c)


def get_by_id(id: ContractId) -> Contract:
    contract_model = ContractModel.objects.get(pk=id)
    return as_domain_object(contract_model)


def all() -> Sequence[Contract]:
    return DomainQuerySet(ContractModel.objects.all(), as_domain_object)


def get_by_name(name: str) -> Contract | None:
    contract = ContractModel.objects.filter(name=name).first()
    if not contract:
        return None

    return as_domain_object(contract)


def get_active_contracts() -> Iterable[Contract]:
    all_contracts = DomainQuerySet(ContractModel.objects.all(), as_domain_object)
    all_active_contracts = LazyCachedIterable(
        contract for contract in all_contracts if contract.is_active()
    )

    return all_active_contracts


def as_domain_object(contract_model: ContractModel) -> Contract:
    return Contract(
        id=ContractId(contract_model.pk),
        name=NonEmptyStr(contract_model.name),
        publishers=LazyCachedIterable(
            PublisherId(p.pk) for p in contract_model.publishers.iterator()
        ),
        journals=LazyCachedIterable(JournalId(j.pk) for j in contract_model.journals.iterator()),
        period=DateRange.create(start=contract_model.start_date, end=contract_model.end_date),
        publication_billing=PublicationBilling(contract_model.publication_billing),
    )


def create(contract: Contract) -> ContractId:
    if contract.id:
        raise ContractAlreadyExists(contract.id)

    if not contract.id:
        contract_model = ContractModel.objects.create(
            name=contract.name,
            start_date=contract.period.start,
            end_date=contract.period.end,
            publication_billing=contract.publication_billing.value,
        )
    else:
        contract_model = ContractModel.objects.get(pk=contract.id)
        contract_model.name = contract.name
        contract_model.start_date = contract.period.start
        contract_model.end_date = contract.period.end
        contract_model.publication_billing = contract.publication_billing.value

    _set_publishers_and_journals(contract, contract_model)
    contract_model.save()
    return ContractId(contract_model.pk)


def update(contract: Contract) -> None:
    if not contract.id:
        raise UnsavedContract(contract)

    contract_model = ContractModel.objects.get(pk=contract.id)
    contract_model.name = contract.name
    contract_model.start_date = contract.period.start
    contract_model.end_date = contract.period.end
    contract_model.publication_billing = contract.publication_billing.value

    _set_publishers_and_journals(contract, contract_model)
    contract_model.save()


def _set_publishers_and_journals(contract: Contract, contract_model: ContractModel) -> None:
    contract_model.publishers.set(contract.publishers)
    contract_model.journals.set(contract.journals)


class ContractAlreadyExists(ValueError):
    def __init__(self, id: ContractId) -> None:
        super().__init__(f"Contract with id {id} already exists")


class UnsavedContract(ValueError):
    def __init__(self, contract: Contract) -> None:
        super().__init__(f"Contract {contract.name} is not saved")
