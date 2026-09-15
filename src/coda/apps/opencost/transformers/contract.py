"""One contract as one openCost contract record.

The rules and the wording below are the report's own: the live-coda transform reaches for the
mappers, the identifier extraction and the messages here rather than restating them, so an
exclusion is said the same way however the contract's data was reached.
"""

from collections.abc import Iterable
from datetime import date

from coda.apps.contracts.models import Contract
from coda.apps.opencost.issues import (
    GlobalWarning,
    ValidationWarning,
    create_warning,
    record_issue,
)
from coda.apps.opencost.models import OpenCostReport, OpenCostReportContract
from coda.apps.opencost.transformers.entities import entity_exclusion, get_institution
from coda.apps.opencost.transformers.invoices import contract_invoices
from coda.coda_itertools import map_or_none
from opencost import (
    ContractCostDataType,
    ContractInvoiceGroupType,
    ContractInvoicePeriodType,
    ContractPrimaryIdentifier,
    ContractPrimaryIdentifierType,
    ContractSecondaryIdentifiersType,
    ContractSecondaryIdType,
    ContractSecondaryIdTypeEnum,
    ContractType,
    ParticipationType,
)

NO_INSTITUTION_MESSAGE = "Contract was excluded entirely: it has no institution name or identifier."
NO_PARTICIPATION_MESSAGE = (
    "Contract was excluded entirely: it has no participation start and end date."
)
NO_ESAC_MESSAGE = "No ESAC ID — the contract is exported with ESAC 'UNKNOWN'."
UNKNOWN_ESAC = "UNKNOWN"
SECONDARY_IDENTIFIER_TYPES = ["OAI", "EZB", "Local"]


def report_contract_to_pydantic(
    report_contract: OpenCostReportContract,
    issues: list[ValidationWarning] | None = None,
) -> ContractType | None:
    institution = get_institution(report_contract)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        record_issue(issues, GlobalWarning.create(report_contract, NO_INSTITUTION_MESSAGE))
        return None

    participation = get_participation(
        report_contract.participation_from, report_contract.participation_to
    )
    if participation is None:
        # XSD requires the participation block with both dates.
        record_issue(issues, create_warning(report_contract, NO_PARTICIPATION_MESSAGE))
        return None

    contract_secondary_identifiers = get_contract_secondary_identifiers(
        (
            identifier.identifier_type,
            identifier.value,
        )
        for identifier in report_contract.secondary_identifiers.all()
    )

    invoice_exclusions: list[ValidationWarning] = []
    cost_data = _get_contract_cost_data(report_contract, invoice_exclusions)
    if cost_data is None:
        # XSD requires at least one invoice_group — without cost data
        # we cannot produce a valid record.
        record_issue(
            issues,
            create_warning(
                report_contract,
                entity_exclusion([w.message for w in invoice_exclusions]),
            ),
        )
        return None

    if issues is not None:
        issues.extend(invoice_exclusions)

    if not report_contract.primary_identifier_value:
        # ESAC is mandatory in the schema, so the contract is exported
        # with the placeholder value instead of a real identifier.
        record_issue(issues, create_warning(report_contract, NO_ESAC_MESSAGE, level="warning"))

    primary_identifier = ContractPrimaryIdentifier(
        value=report_contract.primary_identifier_value or UNKNOWN_ESAC,
        type=ContractPrimaryIdentifierType.ESAC,
    )

    return ContractType(
        contract_name=report_contract.contract_name,
        institution=institution,
        participation=participation,
        primary_identifier=primary_identifier,
        secondary_identifiers=contract_secondary_identifiers,
        cost_data=cost_data,
    )


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


def _get_contract_cost_data(
    report_item: OpenCostReportContract,
    issues: list[ValidationWarning] | None,
) -> ContractCostDataType | None:
    report_invoices = report_item.invoices.all()
    invoice_list = contract_invoices(report_item, issues)
    if invoice_list is None:
        # XSD requires at least one invoice_group — nothing to produce.
        return None

    first_invoice = report_invoices[0]

    if not first_invoice.group_id or not report_item.report:
        # XSD requires group_id and invoices_period — nothing to produce.
        return None

    invoices_period = invoices_period_of(report_item.report)

    invoice_group = ContractInvoiceGroupType(
        group_id=first_invoice.group_id,
        invoices_period=invoices_period,
        invoice=invoice_list,
    )

    return ContractCostDataType(invoice_group=[invoice_group])


def invoices_period_of(report: OpenCostReport) -> ContractInvoicePeriodType:
    """The period a contract's cost block reports its invoices for."""
    return ContractInvoicePeriodType(
        from_=str(report.period_start),
        to=str(report.period_end),
    )
