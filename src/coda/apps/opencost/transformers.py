import logging
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Literal

from django.urls import reverse

from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportContractSecondaryIdentifier,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportInvoice,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
    OpenCostReportPublicationLink,
)
from coda.coda_itertools import map_or_none
from opencost import (
    AmountInvoice,
    BibliographicInformation,
    CoarPublicationType,
    ContractAmountPaidType,
    ContractAmountsPaid,
    ContractCostDataType,
    ContractCostType,
    ContractInvoiceGroupType,
    ContractInvoicePeriodType,
    ContractInvoiceType,
    ContractPrimaryIdentifier,
    ContractPrimaryIdentifierType,
    ContractSecondaryIdentifiersType,
    ContractSecondaryIdType,
    ContractSecondaryIdTypeEnum,
    ContractType,
    Data,
    Dates,
    InstitutionId,
    InstitutionIdType,
    InstitutionName,
    InstitutionNameType,
    InstitutionType,
    ParticipationType,
    PartOfContractType,
    PublicationAmountPaidType,
    PublicationAmountsPaid,
    PublicationCostDataType,
    PublicationCostType,
    PublicationInvoiceType,
    PublicationPrimaryIdentifier,
    PublicationSecondaryIdentifiers,
    PublicationSecondaryIdType,
    PublicationSecondaryIdTypeEnum,
    PublicationType,
)

logger = logging.getLogger(__name__)


def report_publication_to_pydantic(
    report_pub: OpenCostReportPublication,
    issues: list[ValidationWarning] | None = None,
) -> PublicationType | None:
    institution = _get_institution(report_pub)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        _record_issue(
            issues,
            _publication_warning(
                report_pub,
                _entity_exclusion(["it has no institution name or identifier"]),
                fix_url=reverse("preferences:global_preferences"),
                entity_type="global",
            ),
        )
        return None

    invoice_exclusions: list[ValidationWarning] = []
    invoice_data = _get_invoice_data(report_pub, invoice_exclusions)

    part_of_contract = _get_part_of_contract(report_pub)

    if invoice_data is None and part_of_contract is None:
        # XSD requires at least one of invoice or part_of_contract.
        # Without cost data we cannot produce a valid record.
        _record_issue(
            issues,
            _publication_warning(
                report_pub,
                _entity_exclusion([w.message for w in invoice_exclusions]),
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
        _record_issue(
            issues,
            _publication_warning(
                report_pub,
                "No DOI — the publication is exported with title and journal instead.",
                level="warning",
            ),
        )
        if not report_pub.publisher:
            _record_issue(
                issues,
                _publication_warning(
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


def _text_or_none(value: str) -> str | None:
    """Blank snapshot text is reported as an absent element, not an empty one."""
    return value or None


def _invoice_dates(invoice_date: date | None) -> Dates | None:
    """Return the dates block, or ``None`` when openCost would have no date at all."""
    if invoice_date is None:
        return None

    return Dates(invoice=str(invoice_date))


def _amount_invoice(amount: Decimal | None, currency: str) -> AmountInvoice | None:
    """Return the invoice total, or ``None`` when amount or currency is unusable."""
    return map_or_none(
        lambda currency_code: AmountInvoice(amount=amount, currency=currency_code),
        currency,
    )


def _invoice_label(report_invoice: OpenCostReportInvoice | OpenCostReportContractInvoice) -> str:
    """Identify an invoice to a human reader."""
    return report_invoice.invoice_number or "Unnumbered invoice"


def _quoted_values(values: Iterable[str]) -> str:
    return ", ".join(sorted(f"'{value}'" for value in set(values)))


def _entity_exclusion(reasons: list[str]) -> str:
    """Collapse the reasons lower-level records were dropped into a single message."""
    reason = (
        "; ".join(r.rstrip(".") for r in reasons)
        if reasons
        else "no reportable invoice data was available"
    )

    return f"Excluded entirely: {reason}."


def _record_issue(issues: list[ValidationWarning] | None, warning: ValidationWarning) -> None:
    """Record why snapshot data is missing from the generated XML."""
    if warning.level == "error":
        logger.warning("%s: %s", warning.entity_name, warning.message)
    else:
        logger.info("%s: %s", warning.entity_name, warning.message)

    if issues is not None:
        issues.append(warning)


def _publication_warning(
    report_pub: OpenCostReportPublication,
    message: str,
    level: Literal["error", "warning"] = "error",
    fix_url: str | None = None,
    entity_type: Literal["publication", "contract", "global"] | None = None,
) -> ValidationWarning:
    return ValidationWarning(
        level=level,
        message=message,
        entity_type=entity_type or "publication",
        entity_id=report_pub.publication_id,
        entity_name=report_pub.title,
        fix_url=fix_url
        or reverse(
            "fundingrequests:detail", kwargs={"pk": report_pub.publication.fundingrequest.id}
        ),
    )


def _contract_warning(
    report_contract: OpenCostReportContract,
    message: str,
    level: Literal["error", "warning"] = "error",
    fix_url: str | None = None,
    entity_type: Literal["publication", "contract", "global"] | None = None,
) -> ValidationWarning:
    return ValidationWarning(
        level=level,
        message=message,
        entity_type=entity_type or "contract",
        entity_id=report_contract.contract_id,
        entity_name=report_contract.contract_name,
        fix_url=fix_url or reverse("contracts:detail", kwargs={"pk": report_contract.contract_id}),
    )


def _get_invoice_data(
    report_pub: OpenCostReportPublication,
    issues: list[ValidationWarning] | None,
) -> list[PublicationInvoiceType] | None:
    invoice_list = []
    for report_invoice in report_pub.invoices.all():
        report_positions = report_invoice.positions.all()
        amounts_paid, unmappable = _publication_amounts_paid(report_positions)
        label = _invoice_label(report_invoice)

        if not amounts_paid:
            # XSD requires at least one amount_paid per invoice.
            _record_issue(
                issues,
                _publication_warning(report_pub, _unusable_positions_message(label, unmappable)),
            )
            continue

        dates = _invoice_dates(report_invoice.invoice_date)
        if dates is None:
            # XSD requires an invoice or payment date.
            _record_issue(
                issues,
                _publication_warning(
                    report_pub, f"Invoice {label} has no invoice date and was excluded."
                ),
            )
            continue

        if unmappable:
            _record_issue(
                issues,
                _publication_warning(
                    report_pub,
                    f"Invoice {label}: {len(unmappable)} of {len(report_positions)} positions "
                    f"with a cost type or currency openCost does not accept "
                    f"({_quoted_values(unmappable)}) were excluded. "
                    f"The invoice in the XML covers only its remaining positions.",
                ),
            )

        # FIXME: The total amount on the invoice is not necessarily the sum of the positions,
        # because some positions may have a cost type that openCost does not know about.
        # Further, currency may differ between positions, so we cannot sum them up.
        # For now, we will sum the positions and use that as the total amount, but this is not ideal.
        total_amount = sum((position.amount for position in report_positions), Decimal(0))

        invoice_list.append(
            PublicationInvoiceType(
                invoice_number=_text_or_none(report_invoice.invoice_number),
                creditor=_text_or_none(report_invoice.creditor),
                amounts_paid=PublicationAmountsPaid(amount_paid=amounts_paid),
                dates=dates,
                amount_invoice=_amount_invoice(
                    amount=total_amount,
                    currency=report_positions[0].currency,
                ),
            )
        )

    return invoice_list or None


def _unusable_positions_message(label: str, unmappable: list[str]) -> str:
    if not unmappable:
        return f"Invoice {label} has no positions and was excluded."

    return (
        f"Invoice {label} has no positions with a cost type or currency openCost accepts "
        f"({_quoted_values(unmappable)}) and was excluded."
    )


def _publication_amounts_paid(
    positions: Iterable[OpenCostReportInvoicePosition],
) -> tuple[list[PublicationAmountPaidType], list[str]]:
    amounts_paid: list[PublicationAmountPaidType] = []
    unmappable: list[str] = []

    for position in positions:
        amount_paid = _publication_amount_paid(position)
        if amount_paid is None:
            unmappable.append(position.cost_type)
        else:
            amounts_paid.append(amount_paid)

    return amounts_paid, unmappable


def _publication_amount_paid(
    position: OpenCostReportInvoicePosition,
) -> PublicationAmountPaidType | None:
    return map_or_none(
        lambda cost_type: PublicationAmountPaidType(
            amount=position.amount,
            currency=position.currency,
            cost_type=PublicationCostType(cost_type),
            vat=position.vat or Decimal(0),
        ),
        position.cost_type,
    )


def _get_institution(
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
        if (identifier := _institution_identifier(inst_id)) is not None
    ]

    # XSD requires at least one name or id (minOccurs=1 on choice).
    # Return None when unavailable so the caller can skip this entity.
    if not names and not identifiers:
        return None

    return InstitutionType(
        name=names if names else None,
        id=identifiers if identifiers else None,
    )


def _institution_identifier(
    inst_id: OpenCostReportInstitutionIdentifier | OpenCostReportContractInstitutionIdentifier,
) -> InstitutionId | None:
    return map_or_none(
        lambda identifier_type: InstitutionId(
            value=inst_id.value, type=InstitutionIdType(identifier_type)
        ),
        inst_id.identifier_type,
    )


def to_opencost(
    report: OpenCostReport,
    publications_list: list[OpenCostReportPublication] | None = None,
    contracts_list: list[OpenCostReportContract] | None = None,
    issues: list[ValidationWarning] | None = None,
) -> Data | None:
    # Use pre-loaded data if provided, otherwise fetch (backwards compatible)
    if publications_list is None:
        publications_list = list(report.publications.all())
    if contracts_list is None:
        contracts_list = list(report.contracts.all())

    publications = [
        pub
        for report_pub in publications_list
        if (pub := report_publication_to_pydantic(report_pub, issues)) is not None
    ]

    contracts = [
        contract
        for report_contract in contracts_list
        if (contract := report_contract_to_pydantic(report_contract, issues)) is not None
    ]

    if not publications and not contracts:
        # OpenCost requires at least one publication or contract
        return None

    return Data(
        publication=publications if publications else None,
        contract=contracts if contracts else None,
    )


def report_contract_to_pydantic(
    report_contract: OpenCostReportContract,
    issues: list[ValidationWarning] | None = None,
) -> ContractType | None:
    institution = _get_institution(report_contract)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        _record_issue(
            issues,
            _contract_warning(
                report_contract,
                "Contract was excluded entirely: it has no institution name or identifier.",
                fix_url=reverse("preferences:global_preferences"),
                entity_type="global",
            ),
        )
        return None

    participation = _participation(report_contract)
    if participation is None:
        # XSD requires the participation block with both dates.
        _record_issue(
            issues,
            _contract_warning(
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
        _record_issue(
            issues,
            _contract_warning(
                report_contract,
                _entity_exclusion([w.message for w in invoice_exclusions]),
            ),
        )
        return None

    if issues is not None:
        issues.extend(invoice_exclusions)

    if not report_contract.primary_identifier_value:
        # ESAC is mandatory in the schema, so the contract is exported
        # with the placeholder value instead of a real identifier.
        _record_issue(
            issues,
            _contract_warning(
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
    report_contract: OpenCostReportContract,
    issues: list[ValidationWarning] | None,
) -> ContractCostDataType | None:
    report_invoices = report_contract.invoices.all()

    invoice_list = []
    for report_invoice in report_invoices:
        report_positions = report_invoice.positions.all()
        amounts_paid, unmappable = _contract_amounts_paid(report_positions)
        label = _invoice_label(report_invoice)

        if not amounts_paid:
            # XSD requires at least one amount_paid per invoice.
            _record_issue(
                issues,
                _contract_warning(report_contract, _unusable_positions_message(label, unmappable)),
            )
            continue

        dates = _invoice_dates(report_invoice.invoice_date)
        if dates is None:
            # XSD requires an invoice or payment date.
            _record_issue(
                issues,
                _contract_warning(
                    report_contract, f"Invoice {label} has no invoice date and was excluded."
                ),
            )
            continue

        if unmappable:
            _record_issue(
                issues,
                _contract_warning(
                    report_contract,
                    f"Invoice {label}: {len(unmappable)} of {len(report_positions)} positions "
                    f"with a cost type or currency openCost does not accept "
                    f"({_quoted_values(unmappable)}) were excluded. "
                    f"The invoice in the XML covers only its remaining positions.",
                ),
            )

        invoice_list.append(
            ContractInvoiceType(
                invoice_number=_text_or_none(report_invoice.invoice_number),
                creditor=_text_or_none(report_invoice.creditor),
                amounts_paid=ContractAmountsPaid(amount_paid=amounts_paid),
                dates=dates,
                amount_invoice=_amount_invoice(
                    amount=report_invoice.amount_invoice,
                    currency=report_invoice.amount_invoice_currency,
                ),
            )
        )

    if not invoice_list:
        # XSD requires at least one invoice_group — nothing to produce.
        return None

    first_invoice = report_invoices[0]

    if not first_invoice.group_id or not report_contract.report:
        # XSD requires group_id and invoices_period — nothing to produce.
        return None

    invoices_period = ContractInvoicePeriodType(
        from_=str(report_contract.report.period_start),
        to=str(report_contract.report.period_end),
    )

    invoice_group = ContractInvoiceGroupType(
        group_id=first_invoice.group_id,
        invoices_period=invoices_period,
        invoice=invoice_list,
    )

    return ContractCostDataType(invoice_group=[invoice_group])


def _contract_amounts_paid(
    positions: Iterable[OpenCostReportContractInvoicePosition],
) -> tuple[list[ContractAmountPaidType], list[str]]:
    amounts_paid: list[ContractAmountPaidType] = []
    unmappable: list[str] = []

    for position in positions:
        amount_paid = _contract_amount_paid(position)
        if amount_paid is None:
            unmappable.append(position.cost_type)
        else:
            amounts_paid.append(amount_paid)

    return amounts_paid, unmappable


def _contract_amount_paid(
    position: OpenCostReportContractInvoicePosition,
) -> ContractAmountPaidType | None:
    return map_or_none(
        lambda cost_type: ContractAmountPaidType(
            amount=position.amount,
            currency=position.currency,
            cost_type=ContractCostType(cost_type),
            vat=position.vat or Decimal(0),
        ),
        position.cost_type,
    )


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
