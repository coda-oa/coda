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
    model.publishers.set(contract.publishers)
    model.journals.set(contract.journals)
