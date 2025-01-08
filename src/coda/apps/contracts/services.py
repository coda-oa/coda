from coda.apps.contracts.models import Contract as ContractModel
from coda.contract import Contract, ContractId, PublisherId
from coda.date import DateRange
from coda.publication import JournalId
from coda.string import NonEmptyStr


def first() -> Contract | None:
    c = ContractModel.objects.first()
    if not c:
        return None

    return as_domain_object(c)


def get_by_id(id: ContractId) -> Contract:
    contract_model = ContractModel.objects.get(pk=id)
    return as_domain_object(contract_model)


def all() -> list[Contract]:
    return [as_domain_object(contract_model) for contract_model in ContractModel.objects.all()]


def as_domain_object(contract_model: ContractModel) -> Contract:
    return Contract(
        id=ContractId(contract_model.pk),
        name=NonEmptyStr(contract_model.name),
        publishers=tuple(PublisherId(p.pk) for p in contract_model.publishers.all()),
        journals=tuple(JournalId(j.pk) for j in contract_model.journals.all()),
        period=DateRange.create(start=contract_model.start_date, end=contract_model.end_date),
    )


def save(contract: Contract) -> ContractId:
    if not contract.id:
        contract_model = ContractModel.objects.create(
            name=contract.name,
            start_date=contract.period.start,
            end_date=contract.period.end,
        )
    else:
        contract_model = ContractModel.objects.get(pk=contract.id)
        contract_model.name = contract.name
        contract_model.start_date = contract.period.start
        contract_model.end_date = contract.period.end

    contract_model.publishers.set(contract.publishers)
    contract_model.journals.set(contract.journals)
    contract_model.save()
    return ContractId(contract_model.pk)
