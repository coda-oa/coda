"""Turning a stored openCost report snapshot into an openCost document.

``to_opencost`` is the only function of this package meant for outside callers: it walks the
snapshot's publications and contracts and returns the document openCost accepts, or ``None``
when the snapshot holds nothing openCost can express. What it left out on the way — entities,
invoices, invoice rows — is collected into the caller's ``issues`` list rather than raised.

The submodules hold one construction each: ``publication`` and ``contract`` for the two kinds
of report item, ``invoices`` for the invoice elements within them, and ``entities`` for the
institution and exclusion wording both of those need. Their per-item builders are reached
directly by the tests that exercise one kind of item alone; nothing outside the tests does.
"""

from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportPublication,
)
from coda.apps.opencost.transformers.contract import report_contract_to_pydantic
from coda.apps.opencost.transformers.publication import report_publication_to_pydantic
from opencost import Data

__all__ = ["to_opencost"]


def to_opencost(
    report: OpenCostReport,
    publications_list: list[OpenCostReportPublication] | None = None,
    contracts_list: list[OpenCostReportContract] | None = None,
    issues: list[ValidationWarning] | None = None,
) -> Data | None:
    """The whole snapshot as one openCost document, plus what had to be left out.

    Pass ``publications_list``/``contracts_list`` when the caller already holds the report
    item tree, so the transform reads the prefetches instead of querying again.
    """
    # Use pre-loaded data if provided, otherwise fetch (backwards compatible)
    if publications_list is None:
        publications_list = list(report.publications.all())
    if contracts_list is None:
        contracts_list = list(report.contracts.all())

    publications = [
        pub
        for report_pub in publications_list
        if (pub := report_publication_to_pydantic(report_pub, issues)) is not None
    ]

    contracts = [
        contract
        for report_contract in contracts_list
        if (contract := report_contract_to_pydantic(report_contract, issues)) is not None
    ]

    if not publications and not contracts:
        # OpenCost requires at least one publication or contract
        return None

    return Data(
        publication=publications if publications else None,
        contract=contracts if contracts else None,
    )
