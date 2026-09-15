"""The rules, wording and identifier builders of one openCost publication record.

These are the report's own rules: the transform reaches for the mappers and the messages here
rather than restating them, so an exclusion is said the same way however the publication's data
was reached.
"""

from collections.abc import Iterable

from coda.apps.contracts.models import Contract
from coda.apps.opencost.issues import ValidationWarning, create_warning, record_issue
from coda.apps.opencost.models import OpenCostReportPublication
from coda.coda_itertools import map_or_none
from opencost import (
    BibliographicInformation,
    CoarPublicationType,
    ContractPrimaryIdentifier,
    ContractPrimaryIdentifierType,
    PartOfContractType,
    PublicationPrimaryIdentifier,
    PublicationSecondaryIdentifiers,
    PublicationSecondaryIdType,
    PublicationSecondaryIdTypeEnum,
)

NO_INSTITUTION_REASON = "it has no institution name or identifier"
NO_DOI_MESSAGE = "No DOI — the publication is exported with title and journal instead."
NO_PUBLISHER_MESSAGE = "No publisher — the publication is exported with 'Unknown Publisher'."
UNKNOWN_PUBLISHER = "Unknown Publisher"


def no_doi_primary_identifier(
    report_item: OpenCostReportPublication,
    title: str,
    publisher: str,
    journal: str,
    issues: list[ValidationWarning] | None,
) -> PublicationPrimaryIdentifier:
    """openCost's fallback for a DOI-less publication: exported with title and journal instead.

    With no publisher either the export says so and names ``Unknown Publisher``.
    """
    record_issue(issues, create_warning(report_item, NO_DOI_MESSAGE, level="warning"))
    if not publisher:
        record_issue(issues, create_warning(report_item, NO_PUBLISHER_MESSAGE, level="warning"))

    return PublicationPrimaryIdentifier(
        bibliographic_information=BibliographicInformation(
            Title=title,
            Publisher=publisher or UNKNOWN_PUBLISHER,
            isPartOf=journal if journal else title,
        )
    )


def get_publication_type(publication_type: str) -> CoarPublicationType:
    return map_or_none(CoarPublicationType, publication_type) or CoarPublicationType.other


def get_secondary_identifiers(
    links: Iterable[tuple[str, str]],
) -> PublicationSecondaryIdentifiers | None:
    secondary_ids = [
        secondary_id
        for link_type, value in links
        if (secondary_id := publication_secondary_id(link_type, value)) is not None
    ]

    if not secondary_ids:
        return None

    return PublicationSecondaryIdentifiers(id=secondary_ids)


def publication_secondary_id(link_type: str, value: str) -> PublicationSecondaryIdType | None:
    return map_or_none(
        lambda link_type_name: PublicationSecondaryIdType(
            value=value, type=PublicationSecondaryIdTypeEnum(link_type_name)
        ),
        link_type,
    )


def part_of_contract(contract: Contract, group_id: str | None) -> PartOfContractType | None:
    """The contract a publication is published under, named by its ESAC identifier.

    ``group_id`` ties the element to the contract's own invoice group; it is absent for a
    contract the report holds no invoices for.
    """
    # Filter in Python to use prefetch cache instead of hitting database
    esac_link = next((link for link in contract.links.all() if link.type.name == "ESAC"), None)

    if not esac_link:
        return None

    primary_identifier = ContractPrimaryIdentifier(
        value=esac_link.value,
        type=ContractPrimaryIdentifierType.ESAC,
    )

    return PartOfContractType(
        primary_identifier=primary_identifier,
        group_id=group_id,
    )
