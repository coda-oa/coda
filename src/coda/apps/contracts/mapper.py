from coda.apps.contracts.models import Contract as ContractModel
from coda.domain.contract import Contract, ContractId, PublicationBilling, PublisherId
from coda.domain.date import DateRange
from coda.domain.publication.publication import JournalId
from coda.domain.string import NonEmptyStr
from coda.coda_itertools import LazyCachedIterable


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
    # Collect all publisher relationships across all contracts
    publisher_through_entries = [
        ContractModel.publishers.through(contract_id=model.pk, publisher_id=publisher_id)
        for contract, model in zip(contracts, models)
        for publisher_id in contract.publishers
    ]

    # Collect all journal relationships across all contracts
    journal_through_entries = [
        ContractModel.journals.through(contract_id=model.pk, journal_id=journal_id)
        for contract, model in zip(contracts, models)
        for journal_id in contract.journals
    ]

    # Bulk insert publisher relationships (single query, or 0 if empty)
    if publisher_through_entries:
        ContractModel.publishers.through.objects.bulk_create(publisher_through_entries)

    # Bulk insert journal relationships (single query, or 0 if empty)
    if journal_through_entries:
        ContractModel.journals.through.objects.bulk_create(journal_through_entries)
