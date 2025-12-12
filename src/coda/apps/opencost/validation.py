from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import OpenCostReport


@dataclass
class ValidationWarning:
    level: Literal["error", "warning"]
    message: str
    entity_type: Literal["contract", "publication", "global"]
    entity_id: int | None = None
    entity_name: str | None = None
    fix_url: str | None = None


def validate_report(report: "OpenCostReport") -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []

    for contract in report.contracts.all():
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

    for pub in report.publications.all():
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
