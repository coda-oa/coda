"""OpenCost entities that more than one kind of report item is built from."""

from collections.abc import Iterable

from coda.apps.opencost.models import (
    OpenCostReportContract,
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
    """The institution a snapshot row recorded."""
    return institution_from(
        report_obj.institution_name,
        (
            (identifier.identifier_type, identifier.value)
            for identifier in report_obj.institution_identifiers.all()
        ),
    )


def institution_from(name: str, identifiers: Iterable[tuple[str, str]]) -> InstitutionType | None:
    """The institution behind a name and its ``(identifier type, value)`` pairs.

    Both arrive as they were recorded for the report: the name may be blank and a pair whose
    type openCost has no member for is dropped.
    """
    names = []
    if name:
        names.append(InstitutionName(value=name, type=InstitutionNameType.full))

    ids = [
        identifier
        for identifier_type, value in identifiers
        if (identifier := institution_identifier(identifier_type, value)) is not None
    ]

    # XSD requires at least one name or id (minOccurs=1 on choice).
    # Return None when unavailable so the caller can skip this entity.
    if not names and not ids:
        return None

    return InstitutionType(
        name=names if names else None,
        id=ids if ids else None,
    )


def institution_identifier(identifier_type: str, value: str) -> InstitutionId | None:
    return map_or_none(
        lambda type_name: InstitutionId(value=value, type=InstitutionIdType(type_name)),
        identifier_type,
    )
