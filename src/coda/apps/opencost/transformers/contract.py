"""The rules, wording and identifier extraction of one openCost contract record.

These are the report's own rules: the transform reaches for the mappers, the identifier extraction
and the messages here rather than restating them, so an exclusion is said the same way however the
contract's data was reached.
"""

from collections.abc import Iterable
from datetime import date

from coda.apps.contracts.models import Contract
from coda.apps.opencost.models import OpenCostReport
from coda.coda_itertools import map_or_none
from opencost import (
    ContractInvoicePeriodType,
    ContractSecondaryIdentifiersType,
    ContractSecondaryIdType,
    ContractSecondaryIdTypeEnum,
    ParticipationType,
)

NO_INSTITUTION_MESSAGE = "Contract was excluded entirely: it has no institution name or identifier."
NO_PARTICIPATION_MESSAGE = (
    "Contract was excluded entirely: it has no participation start and end date."
)
NO_ESAC_MESSAGE = "No ESAC ID — the contract is exported with ESAC 'UNKNOWN'."
UNKNOWN_ESAC = "UNKNOWN"
SECONDARY_IDENTIFIER_TYPES = ["OAI", "EZB", "Local"]


def get_participation(from_: date | None, to: date | None) -> ParticipationType | None:
    if not from_ or not to:
        return None

    return ParticipationType(from_=str(from_), to=str(to))


def get_contract_secondary_identifiers(
    identifiers: Iterable[tuple[str, str]],
) -> ContractSecondaryIdentifiersType | None:
    secondary_ids = [
        secondary_id
        for identifier_type, value in identifiers
        if (secondary_id := contract_secondary_id(identifier_type, value)) is not None
    ]

    if not secondary_ids:
        return None

    return ContractSecondaryIdentifiersType(id=secondary_ids)


def contract_secondary_id(identifier_type: str, value: str) -> ContractSecondaryIdType | None:
    return map_or_none(
        lambda identifier_type_name: ContractSecondaryIdType(
            value=value, type=ContractSecondaryIdTypeEnum(identifier_type_name)
        ),
        identifier_type,
    )


def get_contract_primary_identifier(contract: Contract) -> str:
    """The ESAC identifier a contract is exported under, empty when it has none.

    Uses prefetched links to avoid additional queries.
    """
    # Use prefetched links, filter in Python
    esac = next((link for link in contract.links.all() if link.type.name == "ESAC"), None)
    if esac:
        return esac.value
    return ""


def secondary_identifiers_from_links(contract: Contract) -> list[tuple[str, str]]:
    """The secondary identifiers (OAI, EZB, Local) a contract's links carry.

    Uses prefetched links to avoid additional queries.
    """
    identifiers = []
    # Use prefetched links, filter in Python
    for link in contract.links.all():
        if link.type.name in SECONDARY_IDENTIFIER_TYPES:
            identifier_type = link.type.name.lower()
            identifiers.append((identifier_type, link.value))
    return identifiers


def invoices_period_of(report: OpenCostReport) -> ContractInvoicePeriodType:
    """The period a contract's cost block reports its invoices for."""
    return ContractInvoicePeriodType(
        from_=str(report.period_start),
        to=str(report.period_end),
    )
