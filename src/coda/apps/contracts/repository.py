from collections.abc import Sequence

from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.domainqueryset import DomainQuerySet
from coda.domain.contract import Contract, ContractId, PublicationBilling, PublisherId
from coda.domain.date import DateRange
from coda.domain.publication import JournalId
from coda.domain.string import NonEmptyStr
from coda.lazyiterable import LazyCachedIterable


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


def save(contract: Contract) -> ContractId:
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

    contract_model.publishers.set(contract.publishers)
    contract_model.journals.set(contract.journals)
    contract_model.save()
    return ContractId(contract_model.pk)
