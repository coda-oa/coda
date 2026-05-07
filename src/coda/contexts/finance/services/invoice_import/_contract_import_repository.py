"""Import-scoped contract repository.

Wraps fetch_or_create_contracts so that parse_into_position can resolve
contract names to Contract domain objects without touching ImportLookups.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from coda.contexts.shared.import_service.contract_lookup import fetch_or_create_contracts
from coda.domain.contract import Contract

if TYPE_CHECKING:
    from coda.contexts.finance.dto.import_dtos import InvoiceImportDto


class ContractImportRepository:
    def __init__(self) -> None:
        self._cache: dict[str, Contract] = {}

    def prefetch(self, invoice_dtos: "Iterable[InvoiceImportDto]") -> None:
        """Bulk load contract name → Contract mappings, creating missing ones."""
        from coda.contexts.finance.dto.import_dtos import ContractPositionImportDto
        from coda.contexts.fundingrequest.dto.import_dtos import ContractImportDto

        contract_refs = [
            ContractImportDto(name=position.contract_name, year=position.contract_year)
            for invoice_dto in invoice_dtos
            for position in invoice_dto.positions
            if isinstance(position, ContractPositionImportDto)
        ]

        if not contract_refs:
            return

        self._cache.update(fetch_or_create_contracts(contract_refs))

    def get(self, contract_name: str) -> Contract:
        """Return the Contract for a contract name.

        Raises:
            KeyError: if the contract_name was not found during prefetch.
        """
        return self._cache[contract_name]
