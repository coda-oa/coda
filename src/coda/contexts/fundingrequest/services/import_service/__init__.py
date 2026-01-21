"""FundingRequest import service.

This package provides functionality to import funding requests from JSON files.
Main entry point is the `import_fundingrequests` function.

Example:
    from coda.contexts.fundingrequest.services.import_service import import_fundingrequests

    with open('requests.json', 'r') as f:
        report = import_fundingrequests(f)
        print(f"Imported {report.valid_requests} requests")
"""

from ._service import import_fundingrequests
from .types import FundingRequestImportReport, FundingRequestProcessingError

__all__ = [
    "import_fundingrequests",
    "FundingRequestImportReport",
    "FundingRequestProcessingError",
]
