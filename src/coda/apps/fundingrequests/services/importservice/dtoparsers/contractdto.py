from coda.apps.contracts import repository as contract_repository
from coda.apps.publications.dto import ContractYearDto
from coda.domain.contract import Contract
from coda.domain.string import NonEmptyStr

from ..dto import ContractImportDto


def parse_dto(import_dto: ContractImportDto) -> ContractYearDto:
    contract = _get_contract(import_dto)
    return ContractYearDto(
        contract=contract.id,
        year=import_dto.year,
    )


def _get_contract(contract_dto: ContractImportDto) -> Contract:
    contract = contract_repository.get_by_name(contract_dto.name)
    if not contract:
        contract = Contract.new(name=NonEmptyStr(contract_dto.name))
        contract.id = contract_repository.create(contract)

    return contract
