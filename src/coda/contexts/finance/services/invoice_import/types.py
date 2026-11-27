"""Type definitions for invoice import functionality."""

from dataclasses import dataclass

from coda.contexts.finance.dto.import_dtos import InvoiceImportDto
from coda.contexts.finance.services.invoice_import._funding_sources import (
    FundingSourceStaging,
)
from coda.domain import errors
from coda.domain.contract import Contract
from coda.domain.finance.invoice_positions import Position
from coda.domain.publication.publication import PublicationId


class InvoiceProcessingError(errors.DomainError):
    def __init__(self, invoice_number: str, reasons: list[str]) -> None:
        super().__init__()
        self.invoice_number = invoice_number
        self.reasons = reasons or []

    def unpack(self) -> tuple[str, list[str]]:
        return self.invoice_number, self.reasons


class InvoiceImportDataError(errors.DomainError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


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

    funding_sources: FundingSourceStaging
    request_id_lookup: dict[str, PublicationId]
    contract_lookup: dict[str, Contract]


@dataclass(frozen=True)
class ParsedInvoice:
    invoice_dto: InvoiceImportDto
    positions: tuple[Position, ...]


@dataclass(frozen=True)
class InvoiceImportFailure:
    invoice_number: str
    errors: tuple[InvoiceProcessingError, ...]


type InvoiceOutcome = ParsedInvoice | InvoiceImportFailure


@dataclass(frozen=True)
class InvoiceImportPlan:
    invoices: tuple[ParsedInvoice, ...]
    lookups: ImportLookups
    failures: tuple[InvoiceImportFailure, ...]

    def errors(self) -> list[InvoiceProcessingError]:
        return [error for failure in self.failures for error in failure.errors]
