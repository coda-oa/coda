from coda.apps.contracts.models import Contract as ContractModel
from coda.domain.contract import Contract


def as_django_model(contract: Contract) -> ContractModel:
    return ContractModel(
        pk=contract.id,
        name=contract.name,
        start_date=contract.period.start,
        end_date=contract.period.end,
        publication_billing=contract.publication_billing.value,
    )


def synchronize_relationships(contract: Contract, model: ContractModel) -> None:
    """Synchronize ManyToMany relationships for a single contract.

    This function should be used for single contract create/update operations.
    For bulk operations, use synchronize_relationships_bulk() instead.

    Args:
        contract: Contract domain object with relationship data
        model: ContractModel Django model to update
    """
    model.publishers.set(contract.publishers)
    model.journals.set(contract.journals)


def synchronize_relationships_bulk(contracts: list[Contract], models: list[ContractModel]) -> None:
    """Bulk synchronize ManyToMany relationships for multiple contracts.

    Uses Django's through-table models to bulk insert relationships,
    avoiding N+1 queries from calling .set() in a loop.

    This function should be used when creating multiple contracts at once.
    For single contract operations, use synchronize_relationships() instead.

    Args:
        contracts: List of Contract domain objects (must match models by index)
        models: List of ContractModel Django models (must have PKs assigned)

    Note:
        - Executes 0 queries if all contracts have empty relationships
        - Executes 1 query for publishers + 1 query for journals when relationships exist
        - Significantly faster than calling .set() in a loop (N×2 queries)
    """
    publisher_through_entries = [
        ContractModel.publishers.through(contract_id=model.pk, publisher_id=publisher_id)
        for contract, model in zip(contracts, models)
        for publisher_id in contract.publishers
    ]

    journal_through_entries = [
        ContractModel.journals.through(contract_id=model.pk, journal_id=journal_id)
        for contract, model in zip(contracts, models)
        for journal_id in contract.journals
    ]

    if publisher_through_entries:
        ContractModel.publishers.through.objects.bulk_create(publisher_through_entries)

    if journal_through_entries:
        ContractModel.journals.through.objects.bulk_create(journal_through_entries)
