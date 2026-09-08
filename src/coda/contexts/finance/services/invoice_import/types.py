"""Type definitions for invoice import functionality."""

from dataclasses import dataclass
from typing import Protocol

from coda.contexts.finance.dto.edit_position_dtos import ItemDto, PositionDto
from coda.domain import errors
from coda.domain.contract import Contract
from coda.domain.finance.funding_sources import FundingSource
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.finance.invoice_positions import Position, PositionItemType
from coda.domain.publication.publication import PublicationId


class PositionParser(Protocol):
    def to_itemdto(self, position: Position) -> ItemDto: ...

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType: ...


class InvoiceProcessingError(errors.DomainError):
    def __init__(self, invoice_number: str, reasons: list[str]) -> None:
        super().__init__()
        self.invoice_number = invoice_number
        self.reasons = reasons or []

    def unpack(self) -> tuple[str, list[str]]:
        return self.invoice_number, self.reasons


@dataclass
class InvoiceImportReport:
    valid_invoices: int
    invalid_invoices: int
    errors: list[InvoiceProcessingError]

    def invoices_with_errors(self) -> list[str]:
        return [err.invoice_number for err in self.errors]


@dataclass
class ImportLookups:
    """Unified lookup structure for invoice import."""

    creditor_lookup: dict[str, CreditorId]
    funding_sources_lookup: dict[str, FundingSourceId]
    request_id_lookup: dict[str, PublicationId]
    contract_lookup: dict[str, Contract]
    funding_assignments_lookup: dict[str, FundingSource]
