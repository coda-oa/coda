"""Invoice import package - JSON invoice import and manual invoice pipeline.

Provides the unified pipeline for both bulk import and manual entry.
"""

from ._position_parser import (
    InvoiceParseError,
    InvoiceTotal,
    PositionParseError,
    invoice_total,
    parse_invoice,
    position_to_dto,
    to_position,
)
from ._service import (
    delete_invoice,
    import_invoices,
    pay_invoice,
    process_manual,
    reset_payment,
    save,
    save_many,
)
from .types import (
    ImportLookups,
    InvoiceImportReport,
    InvoiceProcessingError,
)

__all__ = [
    # Bulk import
    "import_invoices",
    "InvoiceImportReport",
    "InvoiceProcessingError",
    # Manual entry
    "process_manual",
    "parse_invoice",
    "to_position",
    "position_to_dto",
    "invoice_total",
    "InvoiceParseError",
    "PositionParseError",
    "InvoiceTotal",
    # Shared persistence
    "save",
    "save_many",
    "pay_invoice",
    "reset_payment",
    "delete_invoice",
    # Types
    "ImportLookups",
]
