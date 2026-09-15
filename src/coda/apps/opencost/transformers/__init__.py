"""Turning a report's items into an openCost document.

``transform_report`` is the entry point: it walks the report's own item rows, reads the live
CODA content behind them, and returns one run's whole result - the document openCost accepts
(its ``data`` is ``None`` when the items hold nothing openCost can express), the issues naming
everything left out, and how every item and invoice row fared. Data that cannot be exported is
reported that way, never raised; the transform raises only ``MissingEntityError``, for a seed
row whose CODA entity vanished since the row was written.

The other modules hold what the transform is made of, not the transform: ``publication`` and
``contract`` the rules, wording and identifier extraction of their kind of report item,
``invoices`` the invoice elements built from a CODA invoice, and ``entities`` the institution
and the exclusion wording both item kinds share. They are the package's internals; callers
outside it import from here.
"""

from coda.apps.opencost.transformers.live import (
    InvoiceOutcome,
    ItemOutcome,
    MissingEntityError,
    get_publisher_and_journal,
    transform_report,
)

__all__ = [
    "InvoiceOutcome",
    "ItemOutcome",
    "MissingEntityError",
    "get_publisher_and_journal",
    "transform_report",
]
