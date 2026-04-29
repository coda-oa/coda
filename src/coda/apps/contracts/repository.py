from collections.abc import Iterable, Sequence

from django.db import transaction

from coda.apps.contracts import django_mapper
from coda.apps.contracts.mappers import ContractDomainMapper
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.domainqueryset import DomainQuerySet
from coda.coda_itertools import LazyCachedIterable
from coda.domain.contract import Contract, ContractId


def first() -> Contract | None:
    c = ContractDomainMapper.prefetch(ContractModel.objects.all()).first()
    if not c:
        return None

    return ContractDomainMapper.map(c)


def get_by_id(id: ContractId) -> Contract:
    contract_model = ContractDomainMapper.prefetch(ContractModel.objects.all()).get(pk=id)
    return ContractDomainMapper.map(contract_model)


def all() -> Sequence[Contract]:
    return DomainQuerySet(
        ContractDomainMapper.prefetch(ContractModel.objects.all()), ContractDomainMapper.map
    )


def get_by_name(name: str) -> Contract | None:
    contract = ContractDomainMapper.prefetch(ContractModel.objects.all()).filter(name=name).first()
    if not contract:
        return None

    return ContractDomainMapper.map(contract)


def find_all_by_names(names: Iterable[str]) -> list[Contract]:
    contracts = ContractDomainMapper.prefetch(
        ContractModel.objects.filter(name__in=names).order_by("id")
    )
    return [ContractDomainMapper.map(contract) for contract in contracts]


def get_active_contracts() -> Iterable[Contract]:
    all_contracts = DomainQuerySet(
        ContractDomainMapper.prefetch(ContractModel.objects.all()), ContractDomainMapper.map
    )
    all_active_contracts = LazyCachedIterable(
        contract for contract in all_contracts if contract.is_active()
    )

    return all_active_contracts


def create(contract: Contract) -> ContractId:
    if contract.id:
        raise ContractAlreadyExists(contract.id)

    contract_model = django_mapper.as_django_model(contract)
    contract_model.save()
    django_mapper.synchronize_relationships(contract, contract_model)
    contract_model.save()
    return ContractId(contract_model.pk)


@transaction.atomic
def create_many(contracts: Iterable[Contract]) -> list[Contract]:
    """Bulk create contracts with optimized ManyToMany relationship handling.

    Creates multiple contracts in a single transaction with bulk through-table
    inserts for publishers and journals, avoiding N+1 query patterns.

    Args:
        contracts: Iterable of Contract domain objects to create

    Returns:
        List of created Contract domain objects with IDs assigned
    """
    contracts = list(contracts)

    if not contracts:
        return []

    models = [django_mapper.as_django_model(contract) for contract in contracts]
    models = ContractModel.objects.bulk_create(models)
    django_mapper.synchronize_relationships_bulk(contracts, models)

    return [ContractDomainMapper.map(model) for model in models]


def update(contract: Contract) -> None:
    if not contract.id:
        raise UnsavedContract(contract)

    contract_model = django_mapper.as_django_model(contract)
    django_mapper.synchronize_relationships(contract, contract_model)
    contract_model.save()


class ContractAlreadyExists(ValueError):
    def __init__(self, id: ContractId) -> None:
        super().__init__(f"Contract with id {id} already exists")


class UnsavedContract(ValueError):
    def __init__(self, contract: Contract) -> None:
        super().__init__(f"Contract {contract.name} is not saved")
