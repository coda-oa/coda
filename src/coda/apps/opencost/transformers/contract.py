"""One snapshotted contract as one openCost contract record."""

from coda.apps.opencost.issues import (
    GlobalWarning,
    ValidationWarning,
    create_warning,
    record_issue,
)
from coda.apps.opencost.models import (
    OpenCostReportContract,
    OpenCostReportContractSecondaryIdentifier,
)
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


def report_contract_to_pydantic(
    report_contract: OpenCostReportContract,
    issues: list[ValidationWarning] | None = None,
) -> ContractType | None:
    institution = get_institution(report_contract)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        record_issue(
            issues,
            GlobalWarning.create(
                report_contract,
                "Contract was excluded entirely: it has no institution name or identifier.",
            ),
        )
        return None

    participation = _participation(report_contract)
    if participation is None:
        # XSD requires the participation block with both dates.
        record_issue(
            issues,
            create_warning(
                report_contract,
                "Contract was excluded entirely: it has no participation start and end date.",
            ),
        )
        return None

    contract_secondary_identifiers = _get_contract_secondary_identifiers(report_contract)

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
        record_issue(
            issues,
            create_warning(
                report_contract,
                "No ESAC ID — the contract is exported with ESAC 'UNKNOWN'.",
                level="warning",
            ),
        )

    primary_identifier = ContractPrimaryIdentifier(
        value=report_contract.primary_identifier_value or "UNKNOWN",
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


def _participation(report_contract: OpenCostReportContract) -> ParticipationType | None:
    if not report_contract.participation_from or not report_contract.participation_to:
        return None

    return ParticipationType(
        from_=str(report_contract.participation_from),
        to=str(report_contract.participation_to),
    )


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

    invoices_period = ContractInvoicePeriodType(
        from_=str(report_item.report.period_start),
        to=str(report_item.report.period_end),
    )

    invoice_group = ContractInvoiceGroupType(
        group_id=first_invoice.group_id,
        invoices_period=invoices_period,
        invoice=invoice_list,
    )

    return ContractCostDataType(invoice_group=[invoice_group])


def _get_contract_secondary_identifiers(
    report_contract: OpenCostReportContract,
) -> ContractSecondaryIdentifiersType | None:
    secondary_ids = [
        secondary_id
        for identifier in report_contract.secondary_identifiers.all()
        if (secondary_id := _contract_secondary_id(identifier)) is not None
    ]

    if not secondary_ids:
        return None

    return ContractSecondaryIdentifiersType(id=secondary_ids)


def _contract_secondary_id(
    identifier: OpenCostReportContractSecondaryIdentifier,
) -> ContractSecondaryIdType | None:
    return map_or_none(
        lambda identifier_type: ContractSecondaryIdType(
            value=identifier.value, type=ContractSecondaryIdTypeEnum(identifier_type)
        ),
        identifier.identifier_type,
    )
