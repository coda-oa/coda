from __future__ import annotations

from typing import TYPE_CHECKING

import opencost
from coda.apps.opencost.transformers import to_opencost

if TYPE_CHECKING:
    from coda.apps.opencost.models import (
        OpenCostReport,
        OpenCostReportContract,
        OpenCostReportPublication,
    )
    from coda.apps.opencost.validation import ValidationWarning


def generate_xml(
    report: OpenCostReport,
    publications: list[OpenCostReportPublication] | None = None,
    contracts: list[OpenCostReportContract] | None = None,
    excluded: list[ValidationWarning] | None = None,
) -> str:
    data = to_opencost(report, publications, contracts, excluded)
    if data is None:
        return ""
    return opencost.to_xml(data)
