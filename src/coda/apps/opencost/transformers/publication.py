"""One snapshotted publication as one openCost publication record."""

from coda.apps.opencost.issues import (
    GlobalWarning,
    ValidationWarning,
    create_warning,
    record_issue,
)
from coda.apps.opencost.models import OpenCostReportPublication, OpenCostReportPublicationLink
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
            GlobalWarning.create(
                report_pub, entity_exclusion(["it has no institution name or identifier"])
            ),
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
        # BibliographicInformation is openCost's fallback for a DOI-less
        # publication: it is exported with title and journal instead.
        record_issue(
            issues,
            create_warning(
                report_pub,
                "No DOI — the publication is exported with title and journal instead.",
                level="warning",
            ),
        )
        if not report_pub.publisher:
            record_issue(
                issues,
                create_warning(
                    report_pub,
                    "No publisher — the publication is exported with 'Unknown Publisher'.",
                    level="warning",
                ),
            )
        bib_info = BibliographicInformation(
            Title=report_pub.title,
            Publisher=report_pub.publisher or "Unknown Publisher",
            isPartOf=report_pub.journal if report_pub.journal else report_pub.title,
        )
        primary_identifier = PublicationPrimaryIdentifier(bibliographic_information=bib_info)

    secondary_identifiers = _get_secondary_identifiers(report_pub)

    publication_type = _get_publication_type(report_pub)

    cost_data = PublicationCostDataType(invoice=invoice_data, part_of_contract=part_of_contract)
    return PublicationType(
        primary_identifier=primary_identifier,
        secondary_identifiers=secondary_identifiers,
        institution=institution,
        publication_type=publication_type,
        external_costsplitting=report_pub.external_costsplitting,
        cost_data=cost_data,
    )


def _get_publication_type(report_pub: OpenCostReportPublication) -> CoarPublicationType:
    publication_type = map_or_none(CoarPublicationType, report_pub.publication_type)
    return publication_type or CoarPublicationType.other


def _get_secondary_identifiers(
    report_pub: OpenCostReportPublication,
) -> PublicationSecondaryIdentifiers | None:
    secondary_ids = [
        secondary_id
        for link in report_pub.links.all()
        if (secondary_id := _publication_secondary_id(link)) is not None
    ]

    if not secondary_ids:
        return None

    return PublicationSecondaryIdentifiers(id=secondary_ids)


def _publication_secondary_id(
    link: OpenCostReportPublicationLink,
) -> PublicationSecondaryIdType | None:
    return map_or_none(
        lambda link_type: PublicationSecondaryIdType(
            value=link.value, type=PublicationSecondaryIdTypeEnum(link_type)
        ),
        link.link_type,
    )


def _get_part_of_contract(report_pub: OpenCostReportPublication) -> PartOfContractType | None:
    linked_contracts = report_pub.linked_contracts.all()

    if not linked_contracts:
        return None

    linked_contract = linked_contracts[0]
    contract = linked_contract.contract

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
        group_id=linked_contract.group_id if linked_contract.group_id else None,
    )
