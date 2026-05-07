"""Type definitions for invoice import functionality."""

from dataclasses import dataclass

from coda.domain import errors


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
