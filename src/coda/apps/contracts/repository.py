from collections.abc import Iterable, Sequence

from django.db import transaction

from coda.apps.contracts import mapper
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.domainqueryset import DomainQuerySet
from coda.domain.contract import Contract, ContractId
from coda.lazyiterable import LazyCachedIterable


def first() -> Contract | None:
    c = ContractModel.objects.first()
    if not c:
        return None

    return mapper.as_domain_object(c)


def get_by_id(id: ContractId) -> Contract:
    contract_model = ContractModel.objects.get(pk=id)
    return mapper.as_domain_object(contract_model)


def all() -> Sequence[Contract]:
    return DomainQuerySet(ContractModel.objects.all(), mapper.as_domain_object)


def get_by_name(name: str) -> Contract | None:
    contract = ContractModel.objects.filter(name=name).first()
    if not contract:
        return None

    return mapper.as_domain_object(contract)


def find_all_by_names(names: Iterable[str]) -> list[Contract]:
    contracts = ContractModel.objects.filter(name__in=names)
    return [mapper.as_domain_object(contract) for contract in contracts]


def get_active_contracts() -> Iterable[Contract]:
    all_contracts = DomainQuerySet(ContractModel.objects.all(), mapper.as_domain_object)
    all_active_contracts = LazyCachedIterable(
        contract for contract in all_contracts if contract.is_active()
    )

    return all_active_contracts


def create(contract: Contract) -> ContractId:
    if contract.id:
        raise ContractAlreadyExists(contract.id)

    contract_model = mapper.as_django_model(contract)
    contract_model.save()
    mapper.synchronize_relationships(contract, contract_model)
    contract_model.save()
    return ContractId(contract_model.pk)


@transaction.atomic
def create_many(contracts: Iterable[Contract]) -> list[Contract]:
    contracts = list(contracts)
    models = [mapper.as_django_model(contract) for contract in contracts]
    models = ContractModel.objects.bulk_create(models)
    for contract, model in zip(contracts, models):
        mapper.synchronize_relationships(contract, model)
    return [mapper.as_domain_object(model) for model in models]


def update(contract: Contract) -> None:
    if not contract.id:
        raise UnsavedContract(contract)

    contract_model = mapper.as_django_model(contract)
    mapper.synchronize_relationships(contract, contract_model)
    contract_model.save()


class ContractAlreadyExists(ValueError):
    def __init__(self, id: ContractId) -> None:
        super().__init__(f"Contract with id {id} already exists")


class UnsavedContract(ValueError):
    def __init__(self, contract: Contract) -> None:
        super().__init__(f"Contract {contract.name} is not saved")
