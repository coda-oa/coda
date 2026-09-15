"""One publication as one openCost publication record.

The rules and the wording below are the report's own: the live-coda transform reaches for the
mappers and the messages here rather than restating them, so an exclusion is said the same way
however the publication's data was reached.
"""

from collections.abc import Iterable

from coda.apps.contracts.models import Contract
from coda.apps.opencost.issues import (
    GlobalWarning,
    ValidationWarning,
    create_warning,
    record_issue,
)
from coda.apps.opencost.models import OpenCostReportPublication
from coda.apps.opencost.transformers.entities import entity_exclusion, get_institution
from coda.apps.opencost.transformers.invoices import publication_invoices
from coda.coda_itertools import map_or_none
from opencost import (
    BibliographicInformation,
    CoarPublicationType,
    ContractPrimaryIdentifier,
    ContractPrimaryIdentifierType,
    PartOfContractType,
    PublicationCostDataType,
    PublicationPrimaryIdentifier,
    PublicationSecondaryIdentifiers,
    PublicationSecondaryIdType,
    PublicationSecondaryIdTypeEnum,
    PublicationType,
)

NO_INSTITUTION_REASON = "it has no institution name or identifier"
NO_DOI_MESSAGE = "No DOI — the publication is exported with title and journal instead."
NO_PUBLISHER_MESSAGE = "No publisher — the publication is exported with 'Unknown Publisher'."
UNKNOWN_PUBLISHER = "Unknown Publisher"


def report_publication_to_pydantic(
    report_pub: OpenCostReportPublication,
    issues: list[ValidationWarning] | None = None,
) -> PublicationType | None:
    institution = get_institution(report_pub)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        record_issue(
            issues,
            GlobalWarning.create(report_pub, entity_exclusion([NO_INSTITUTION_REASON])),
        )
        return None

    invoice_exclusions: list[ValidationWarning] = []
    invoice_data = publication_invoices(report_pub, invoice_exclusions)

    part_of_contract = _get_part_of_contract(report_pub)

    if invoice_data is None and part_of_contract is None:
        # XSD requires at least one of invoice or part_of_contract.
        # Without cost data we cannot produce a valid record.
        record_issue(
            issues,
            create_warning(
                report_pub,
                entity_exclusion([w.message for w in invoice_exclusions]),
            ),
        )
        return None

    if issues is not None:
        issues.extend(invoice_exclusions)

    if report_pub.doi:
        primary_identifier = PublicationPrimaryIdentifier(doi=report_pub.doi)
    else:
        primary_identifier = no_doi_primary_identifier(
            report_pub, report_pub.title, report_pub.publisher, report_pub.journal, issues
        )

    secondary_identifiers = get_secondary_identifiers(
        (link.link_type, link.value) for link in report_pub.links.all()
    )

    publication_type = get_publication_type(report_pub.publication_type)

    cost_data = PublicationCostDataType(invoice=invoice_data, part_of_contract=part_of_contract)
    return PublicationType(
        primary_identifier=primary_identifier,
        secondary_identifiers=secondary_identifiers,
        institution=institution,
        publication_type=publication_type,
        external_costsplitting=report_pub.external_costsplitting,
        cost_data=cost_data,
    )


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


def _get_part_of_contract(report_pub: OpenCostReportPublication) -> PartOfContractType | None:
    linked_contracts = report_pub.linked_contracts.all()

    if not linked_contracts:
        return None

    linked_contract = linked_contracts[0]

    return part_of_contract(linked_contract.contract, linked_contract.group_id or None)


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
