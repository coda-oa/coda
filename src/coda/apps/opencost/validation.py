from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING
from collections.abc import Sequence

if TYPE_CHECKING:
    from .models import OpenCostReport, OpenCostReportContract, OpenCostReportPublication


@dataclass
class ValidationWarning:
    level: Literal["error", "warning"]
    message: str
    entity_type: Literal["contract", "publication", "global"]
    entity_id: int | None = None
    entity_name: str | None = None
    fix_url: str | None = None


def validate_report(
    report: "OpenCostReport",
    contracts: Sequence["OpenCostReportContract"] | None = None,
    publications: Sequence["OpenCostReportPublication"] | None = None,
) -> list[ValidationWarning]:
    """
    Validate a report for completeness issues.

    Args:
        report: The OpenCost report to validate
        contracts: Optional pre-loaded contracts (avoids duplicate query)
        publications: Optional pre-loaded publications (avoids duplicate query)

    Returns:
        List of validation warnings/errors
    """
    warnings: list[ValidationWarning] = []

    # Only fetch if not provided (for backwards compatibility)
    if contracts is None:
        contracts = list(report.contracts.select_related("contract").all())
    if publications is None:
        publications = list(report.publications.select_related("publication").all())

    for contract in contracts:
        if not contract.primary_identifier_value:
            warnings.append(
                ValidationWarning(
                    level="error",
                    message="Missing ESAC ID",
                    entity_type="contract",
                    entity_id=contract.contract.id,
                    entity_name=contract.contract_name,
                    fix_url=f"/contracts/{contract.contract.id}/",
                )
            )

        if not contract.institution_name:
            warnings.append(
                ValidationWarning(
                    level="error",
                    message="Missing institution name. Set home institution in preferences.",
                    entity_type="global",
                    entity_id=contract.contract.id,
                    entity_name=contract.contract_name,
                    fix_url="/preferences/",
                )
            )

    for pub in publications:
        if not pub.doi:
            warnings.append(
                ValidationWarning(
                    level="warning",
                    message="Missing DOI",
                    entity_type="publication",
                    entity_id=pub.publication.id,
                    entity_name=pub.title,
                    fix_url=f"/fundingrequests/{pub.publication.id}/",
                )
            )

        if not pub.institution_name:
            warnings.append(
                ValidationWarning(
                    level="error",
                    message="Missing institution name. Set home institution in preferences.",
                    entity_type="global",
                    entity_id=pub.publication.id,
                    entity_name=pub.title,
                    fix_url="/preferences/",
                )
            )

    return warnings
