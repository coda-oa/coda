"""Invoice import package - JSON invoice import functionality.

This package provides functionality to import invoices from JSON files.
The main entry point is the `import_invoices` function.

Example:
    from coda.contexts.finance.services.invoice_import import import_invoices

    with open('invoices.json', 'r') as f:
        report = import_invoices(f)
        print(f"Imported {report.valid_invoices} invoices")
"""

from ._service import import_invoices
from .types import (
    InvoiceImportReport,
    InvoiceProcessingError,
)

__all__ = [
    "import_invoices",  # Main public API function
    "InvoiceImportReport",  # Return type
    "InvoiceProcessingError",  # Error type
]
