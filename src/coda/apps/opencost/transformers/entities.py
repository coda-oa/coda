"""OpenCost entities that more than one kind of report item is built from."""

from coda.apps.opencost.models import (
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportPublication,
)
from coda.coda_itertools import map_or_none
from opencost import (
    InstitutionId,
    InstitutionIdType,
    InstitutionName,
    InstitutionNameType,
    InstitutionType,
)


def entity_exclusion(reasons: list[str]) -> str:
    """Collapse the reasons lower-level records were dropped into a single message."""
    reason = (
        "; ".join(r.rstrip(".") for r in reasons)
        if reasons
        else "no reportable invoice data was available"
    )

    return f"Excluded entirely: {reason}."


def get_institution(
    report_obj: OpenCostReportPublication | OpenCostReportContract,
) -> InstitutionType | None:
    names = []
    if report_obj.institution_name:
        names.append(
            InstitutionName(value=report_obj.institution_name, type=InstitutionNameType.full)
        )

    identifiers = [
        identifier
        for inst_id in report_obj.institution_identifiers.all()
        if (identifier := get_institution_identifier(inst_id)) is not None
    ]

    # XSD requires at least one name or id (minOccurs=1 on choice).
    # Return None when unavailable so the caller can skip this entity.
    if not names and not identifiers:
        return None

    return InstitutionType(
        name=names if names else None,
        id=identifiers if identifiers else None,
    )


def get_institution_identifier(
    inst_id: OpenCostReportInstitutionIdentifier | OpenCostReportContractInstitutionIdentifier,
) -> InstitutionId | None:
    return map_or_none(
        lambda identifier_type: InstitutionId(
            value=inst_id.value, type=InstitutionIdType(identifier_type)
        ),
        inst_id.identifier_type,
    )
