"""The snapshot→XML transform as frozen history, for the one migration that needs it.

Reports generated before ``xml_content`` existed hold their document nowhere but in their
snapshot tree: the publication, contract, invoice and position rows generation recorded.
This module replays the transform of that moment over those rows, so a legacy report's stored
document says what its download said then - the snapshot's wording, the snapshot's data -
rather than whatever live CODA records would now say. It is frozen on purpose: it must keep
replaying the same bytes forever, so it imports nothing from the application (models,
transformers and issue builders all evolve) and reaches the database only through the
historical apps registry the migration hands it.

Read orders are the transform's own: rows come back in the order the snapshot models' ``Meta``
states them, and where a ``Meta`` leaves a tie unbroken the order the original transform's
query answered with is reproduced by running that same query - the stored document is only
ever as ordered as the sort that wrote it. The messages below are copies of the wording
generation used at freeze time - verbatim, because the stored issue log is compared against
them.
"""

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from django.db import migrations, transaction
from django.db.models import Prefetch
from django.urls import reverse

import opencost
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

# --- the wording, verbatim from the transform this module freezes -----------------------

NO_INSTITUTION_REASON = "it has no institution name or identifier"
NO_DOI_MESSAGE = "No DOI — the publication is exported with title and journal instead."
NO_PUBLISHER_MESSAGE = "No publisher — the publication is exported with 'Unknown Publisher'."
UNKNOWN_PUBLISHER = "Unknown Publisher"

NO_INSTITUTION_MESSAGE = "Contract was excluded entirely: it has no institution name or identifier."
NO_PARTICIPATION_MESSAGE = (
    "Contract was excluded entirely: it has no participation start and end date."
)
NO_ESAC_MESSAGE = "No ESAC ID — the contract is exported with ESAC 'UNKNOWN'."
UNKNOWN_ESAC = "UNKNOWN"


def _no_invoice_date_warning_message(label: str) -> str:
    return f"Invoice {label} has no invoice date and was excluded."


def _no_positions_warning_message(label: str, rejected_cost_types: list[str]) -> str:
    if not rejected_cost_types:
        return f"Invoice {label} has no positions and was excluded."

    return (
        f"Invoice {label} has no positions with a cost type or currency openCost accepts "
        f"({_quoted_values(rejected_cost_types)}) and was excluded."
    )


def _excluded_positions_warning_message(
    label: str, rejected_cost_types: list[str], number_of_report_positions: int
) -> str:
    return (
        f"Invoice {label}: {len(rejected_cost_types)} of {number_of_report_positions} positions "
        + "with a cost type or currency openCost does not accept "
        + f"({_quoted_values(rejected_cost_types)}) were excluded. "
        + "The invoice in the XML covers only its remaining positions."
    )


def _entity_exclusion(reasons: list[str]) -> str:
    """Collapse the reasons lower-level records were dropped into a single message."""
    reason = (
        "; ".join(r.rstrip(".") for r in reasons)
        if reasons
        else "no reportable invoice data was available"
    )

    return f"Excluded entirely: {reason}."


def _quoted_values(values: Iterable[str]) -> str:
    return ", ".join(sorted(f"'{value}'" for value in set(values)))


# --- the issue payload, same fields in the same order asdict serialises them ------------


@dataclass
class ValidationWarning:
    level: Literal["error", "warning"]
    message: str
    entity_type: Literal["contract", "publication", "global"]
    entity_id: int | None = None
    entity_name: str | None = None
    fix_url: str | None = None


def _record_issue(issues: list[ValidationWarning] | None, warning: ValidationWarning) -> None:
    """Record why snapshot data is missing from the generated XML."""
    if warning.level == "error":
        logger.warning("%s: %s", warning.entity_name, warning.message)
    else:
        logger.info("%s: %s", warning.entity_name, warning.message)

    if issues is not None:
        issues.append(warning)


def _is_publication_row(item: Any) -> bool:
    return item._meta.model_name == "opencostreportpublication"


def _create_warning(
    item: Any, message: str, level: Literal["error", "warning"] = "error"
) -> ValidationWarning:
    """A warning about one report item, fixed up at the item's own record.

    A publication's fix-up target is the request it was filed under; the request is part of
    the publication's own record, and a snapshot whose publication has lost it is broken
    data the caller's savepoint is there to catch.
    """
    if _is_publication_row(item):
        return ValidationWarning(
            level=level,
            message=message,
            entity_type="publication",
            entity_id=item.publication_id,
            entity_name=item.title,
            fix_url=reverse(
                "fundingrequests:detail", kwargs={"pk": item.publication.fundingrequest.id}
            ),
        )

    return ValidationWarning(
        level=level,
        message=message,
        entity_type="contract",
        entity_id=item.contract_id,
        entity_name=item.contract_name,
        fix_url=reverse("contracts:detail", kwargs={"pk": item.contract_id}),
    )


def _create_global_warning(
    item: Any, message: str, level: Literal["error", "warning"] = "error"
) -> ValidationWarning:
    """An exclusion caused by globally configured data (institution settings).

    Entity identity is that of the item the warning is reported on; only the
    fix URL points at the global preferences.
    """
    warning = _create_warning(item, message, level)
    warning.entity_type = "global"
    warning.fix_url = reverse("preferences:global_preferences")
    return warning


# --- shared mechanics --------------------------------------------------------------------


def _map_or_none[T](map_fn: Callable[[str], T], value: str | None) -> T | None:
    """Map ``value``, treating a falsy value or a ``ValueError`` as absent.

    ``ValueError`` is deliberately the catch-all: pydantic's ``ValidationError``
    subclasses it, so a rejected enum member and a rejected field value both
    yield ``None`` instead of aborting the caller.
    """
    if value:
        try:
            return map_fn(value)
        except ValueError:
            return None

    return None


def _text_or_none(value: str) -> str | None:
    """Blank snapshot text is reported as an absent element, not an empty one."""
    return value or None


# --- institutions ------------------------------------------------------------------------


def _institution_identifier(identifier_type: str, value: str) -> InstitutionId | None:
    return _map_or_none(
        lambda type_name: InstitutionId(value=value, type=InstitutionIdType(type_name)),
        identifier_type,
    )


def _institution_from(name: str, identifiers: Iterable[tuple[str, str]]) -> InstitutionType | None:
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
        if (identifier := _institution_identifier(identifier_type, value)) is not None
    ]

    # XSD requires at least one name or id (minOccurs=1 on choice).
    # Return None when unavailable so the caller can skip this entity.
    if not names and not ids:
        return None

    return InstitutionType(
        name=names if names else None,
        id=ids if ids else None,
    )


def _institution_of(report_obj: Any) -> InstitutionType | None:
    """The institution a snapshot row recorded."""
    return _institution_from(
        report_obj.institution_name,
        (
            (identifier.identifier_type, identifier.value)
            for identifier in report_obj.institution_identifiers.all()
        ),
    )


# --- invoices ----------------------------------------------------------------------------


def _amount_invoice(amount: Decimal | None, currency: str) -> AmountInvoice | None:
    """The invoice total, or ``None`` when openCost cannot be given an amount and currency.

    The amount keeps the precision it arrives at; the XML writer is what formats it. An unusable
    currency is rejected by openCost's own model, which raises a ``ValueError`` subclass that
    ``_map_or_none`` turns into an absent element.
    """
    return _map_or_none(
        lambda currency_code: AmountInvoice(amount=amount, currency=currency_code),
        currency,
    )


def _publication_total(rows: Sequence[Any]) -> AmountInvoice | None:
    """Total over every position held for this invoice.

    Every row counts, including ones openCost was given no cost type for, so the total can
    exceed the sum of the exported amounts: openCost asks for the price as stated on the
    invoice, not for the sum of its items. Currency comes from the first row, which both row
    sources order by amount; CODA stamps one currency on every position of an invoice, so
    which row is asked is moot for invoices CODA created.
    """
    if not rows:
        return None

    total_amount = sum((row.amount for row in rows), Decimal(0))
    return _amount_invoice(total_amount, rows[0].currency)


def _amount_paid(paid_type: Callable[..., Any], cost_type: type, position: Any) -> Any | None:
    """One exported amount, or ``None`` when the snapshot row cannot be given one.

    Amounts go through at the precision the snapshot holds them at, so the exported
    number is the snapshotted number and not a re-rounded copy of it.
    """
    return _map_or_none(
        lambda raw_cost_type: paid_type(
            amount=position.amount,
            currency=position.currency,
            cost_type=cost_type(raw_cost_type),
            vat=position.vat or Decimal(0),
        ),
        position.cost_type,
    )


def _amounts_for(
    paid_type: Callable[..., Any], cost_type: type, positions: Iterable[Any]
) -> tuple[list[Any], list[str], int]:
    """One amount per snapshot row openCost can be given an amount for.

    Alongside the amounts: the cost types of the rows that were not (the cost type is what
    names the position to a reader) and the number of rows asked about at all.
    """
    rows = list(positions)
    items: list[Any] = []
    rejected_cost_types: list[str] = []

    for position in rows:
        amount_paid = _amount_paid(paid_type, cost_type, position)
        if amount_paid is None:
            # None means an unusable cost type, amount or currency.
            rejected_cost_types.append(position.cost_type)
        else:
            items.append(amount_paid)

    return items, rejected_cost_types, len(rows)


def _invoice_label(report_invoice: Any) -> str:
    """Identify an invoice to a human reader."""
    return report_invoice.invoice_number or "Unnumbered invoice"


def _invoice_dates(invoice_date: date | None) -> Dates | None:
    """Return the dates block, or ``None`` when openCost would have no date at all."""
    if invoice_date is None:
        return None

    return Dates(invoice=str(invoice_date))


def _dates_if_exportable(
    report_item: Any,
    report_invoice: Any,
    issues: list[ValidationWarning] | None,
    amounts: tuple[list[Any], list[str], int],
) -> Dates | None:
    """The dates block, or ``None`` when this invoice may not be exported — saying why.

    openCost requires a date and at least one amount-paid element per invoice, so an invoice
    missing either is left out and reported rather than exported in a form the schema rejects.
    Rows openCost could not be given an amount for do not hold the invoice back; they are
    reported alongside the invoice that was built without them.
    """
    label = _invoice_label(report_invoice)
    items, rejected_cost_types, row_count = amounts
    dates = _invoice_dates(report_invoice.invoice_date)

    if dates is None:
        # XSD requires an invoice or payment date.
        _record_issue(issues, _create_warning(report_item, _no_invoice_date_warning_message(label)))
        return None

    if not items:
        # XSD requires at least one amount_paid per invoice.
        _record_issue(
            issues,
            _create_warning(report_item, _no_positions_warning_message(label, rejected_cost_types)),
        )
        return None

    if rejected_cost_types:
        _record_issue(
            issues,
            _create_warning(
                report_item,
                _excluded_positions_warning_message(label, rejected_cost_types, row_count),
            ),
        )

    return dates


def _publication_invoice(
    report_item: Any,
    report_invoice: Any,
    positions: Iterable[Any],
    issues: list[ValidationWarning] | None,
) -> PublicationInvoiceType | None:
    """One invoice element, or ``None`` when openCost cannot be given this invoice at all."""
    rows = list(positions)
    amounts = _amounts_for(PublicationAmountPaidType, PublicationCostType, rows)
    dates = _dates_if_exportable(report_item, report_invoice, issues, amounts)
    if dates is None:
        return None

    return PublicationInvoiceType(
        invoice_number=_text_or_none(report_invoice.invoice_number),
        creditor=_text_or_none(report_invoice.creditor),
        amounts_paid=PublicationAmountsPaid(amount_paid=amounts[0]),
        dates=dates,
        amount_invoice=_publication_total(rows),
    )


def _contract_invoice(
    report_item: Any,
    report_invoice: Any,
    positions: Iterable[Any],
    total_amount: Decimal | None,
    total_currency: str,
    issues: list[ValidationWarning] | None,
) -> ContractInvoiceType | None:
    """One contract invoice element.

    ``total_amount``/``total_currency`` is the price stated on the invoice over all its
    positions, rejected cost types included: the report's own invoice row holds the total
    computed when it was collected.
    """
    amounts = _amounts_for(ContractAmountPaidType, ContractCostType, positions)
    dates = _dates_if_exportable(report_item, report_invoice, issues, amounts)
    if dates is None:
        return None

    return ContractInvoiceType(
        invoice_number=_text_or_none(report_invoice.invoice_number),
        creditor=_text_or_none(report_invoice.creditor),
        amounts_paid=ContractAmountsPaid(amount_paid=amounts[0]),
        dates=dates,
        amount_invoice=_amount_invoice(total_amount, total_currency),
    )


# --- publications ------------------------------------------------------------------------


def _no_doi_primary_identifier(
    report_item: Any,
    title: str,
    publisher: str,
    journal: str,
    issues: list[ValidationWarning] | None,
) -> PublicationPrimaryIdentifier:
    """openCost's fallback for a DOI-less publication: exported with title and journal instead.

    With no publisher either the export says so and names ``Unknown Publisher``.
    """
    _record_issue(issues, _create_warning(report_item, NO_DOI_MESSAGE, level="warning"))
    if not publisher:
        _record_issue(issues, _create_warning(report_item, NO_PUBLISHER_MESSAGE, level="warning"))

    return PublicationPrimaryIdentifier(
        bibliographic_information=BibliographicInformation(
            Title=title,
            Publisher=publisher or UNKNOWN_PUBLISHER,
            isPartOf=journal if journal else title,
        )
    )


def _get_publication_type(publication_type: str) -> CoarPublicationType:
    return _map_or_none(CoarPublicationType, publication_type) or CoarPublicationType.other


def _publication_secondary_id(link_type: str, value: str) -> PublicationSecondaryIdType | None:
    return _map_or_none(
        lambda link_type_name: PublicationSecondaryIdType(
            value=value, type=PublicationSecondaryIdTypeEnum(link_type_name)
        ),
        link_type,
    )


def _get_secondary_identifiers(
    links: Iterable[tuple[str, str]],
) -> PublicationSecondaryIdentifiers | None:
    secondary_ids = [
        secondary_id
        for link_type, value in links
        if (secondary_id := _publication_secondary_id(link_type, value)) is not None
    ]

    if not secondary_ids:
        return None

    return PublicationSecondaryIdentifiers(id=secondary_ids)


def _get_part_of_contract(
    report_pub: Any, esac_values: dict[int, str]
) -> PartOfContractType | None:
    """The contract a publication is published under, named by its ESAC identifier.

    The link's ``group_id`` ties the element to the contract's own invoice group; it is
    absent for a contract the report holds no invoices for. A contract with no recorded ESAC
    value cannot be named at all.
    """
    linked_contracts = report_pub.linked_contracts.all()

    if not linked_contracts:
        return None

    linked_contract = linked_contracts[0]
    esac_value = esac_values.get(linked_contract.contract_id)

    if not esac_value:
        return None

    primary_identifier = ContractPrimaryIdentifier(
        value=esac_value,
        type=ContractPrimaryIdentifierType.ESAC,
    )

    return PartOfContractType(
        primary_identifier=primary_identifier,
        group_id=linked_contract.group_id or None,
    )


def _publication_element(
    report_pub: Any,
    issues: list[ValidationWarning],
    esac_values: dict[int, str],
) -> tuple[PublicationType | None, list[tuple[Any, bool, bool, int | None]]]:
    """One snapshot publication as an openCost element, plus how each of its invoices fared.

    The second half of the result covers every invoice row of the publication as
    ``(row, exported, had_errors, xml_index)``: rows the walk never reached inherit the
    exclusion their parent hit, and an excluded row never carries an index.
    """
    invoice_outcomes: list[tuple[Any, bool, bool, int | None]] = []

    institution = _institution_of(report_pub)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        _record_issue(
            issues,
            _create_global_warning(report_pub, _entity_exclusion([NO_INSTITUTION_REASON])),
        )
        # The walk below never runs; every invoice inherits the parent's exclusion.
        invoice_outcomes.extend((row, False, True, None) for row in report_pub.invoices.all())
        return None, invoice_outcomes

    invoice_exclusions: list[ValidationWarning] = []
    invoice_elements: list[PublicationInvoiceType] = []
    for report_invoice in report_pub.invoices.all():
        row_issues: list[ValidationWarning] = []
        invoice = _publication_invoice(
            report_pub, report_invoice, report_invoice.positions.all(), row_issues
        )
        if invoice is None:
            invoice_outcomes.append((report_invoice, False, True, None))
        else:
            invoice_elements.append(invoice)
            invoice_outcomes.append(
                (
                    report_invoice,
                    True,
                    any(warning.level == "error" for warning in row_issues),
                    len(invoice_elements) - 1,
                )
            )
        invoice_exclusions.extend(row_issues)

    invoice_data = invoice_elements or None

    part_of_contract = _get_part_of_contract(report_pub, esac_values)

    if invoice_data is None and part_of_contract is None:
        # XSD requires at least one of invoice or part_of_contract.
        # Without cost data we cannot produce a valid record.
        _record_issue(
            issues,
            _create_warning(
                report_pub,
                _entity_exclusion([w.message for w in invoice_exclusions]),
            ),
        )
        return None, invoice_outcomes

    issues.extend(invoice_exclusions)

    if report_pub.doi:
        primary_identifier = PublicationPrimaryIdentifier(doi=report_pub.doi)
    else:
        primary_identifier = _no_doi_primary_identifier(
            report_pub, report_pub.title, report_pub.publisher, report_pub.journal, issues
        )

    secondary_identifiers = _get_secondary_identifiers(
        (link.link_type, link.value) for link in report_pub.links.all()
    )

    publication_type = _get_publication_type(report_pub.publication_type)

    cost_data = PublicationCostDataType(invoice=invoice_data, part_of_contract=part_of_contract)
    return (
        PublicationType(
            primary_identifier=primary_identifier,
            secondary_identifiers=secondary_identifiers,
            institution=institution,
            publication_type=publication_type,
            external_costsplitting=report_pub.external_costsplitting,
            cost_data=cost_data,
        ),
        invoice_outcomes,
    )


# --- contracts ---------------------------------------------------------------------------


def _get_participation(from_: date | None, to: date | None) -> ParticipationType | None:
    if not from_ or not to:
        return None

    return ParticipationType(from_=str(from_), to=str(to))


def _contract_secondary_id(identifier_type: str, value: str) -> ContractSecondaryIdType | None:
    return _map_or_none(
        lambda identifier_type_name: ContractSecondaryIdType(
            value=value, type=ContractSecondaryIdTypeEnum(identifier_type_name)
        ),
        identifier_type,
    )


def _get_contract_secondary_identifiers(
    identifiers: Iterable[tuple[str, str]],
) -> ContractSecondaryIdentifiersType | None:
    secondary_ids = [
        secondary_id
        for identifier_type, value in identifiers
        if (secondary_id := _contract_secondary_id(identifier_type, value)) is not None
    ]

    if not secondary_ids:
        return None

    return ContractSecondaryIdentifiersType(id=secondary_ids)


def _invoices_period_of(report: Any) -> ContractInvoicePeriodType:
    """The period a contract's cost block reports its invoices for."""
    return ContractInvoicePeriodType(
        from_=str(report.period_start),
        to=str(report.period_end),
    )


def _get_contract_cost_data(
    report_item: Any,
    invoice_elements: list[ContractInvoiceType],
) -> ContractCostDataType | None:
    """The contract's single invoice group, or ``None`` when it cannot be stated.

    The group is named by the first invoice row's group id - the same one every invoice row
    of this contract's snapshot carries - and reports for the report's own period.
    """
    if not invoice_elements:
        # XSD requires at least one invoice_group — nothing to produce.
        return None

    report_invoices = report_item.invoices.all()
    first_invoice = report_invoices[0]

    if not first_invoice.group_id or not report_item.report:
        # XSD requires group_id and invoices_period — nothing to produce.
        return None

    invoice_group = ContractInvoiceGroupType(
        group_id=first_invoice.group_id,
        invoices_period=_invoices_period_of(report_item.report),
        invoice=invoice_elements,
    )

    return ContractCostDataType(invoice_group=[invoice_group])


def _contract_element(
    report_contract: Any,
    issues: list[ValidationWarning],
) -> tuple[ContractType | None, list[tuple[Any, bool, bool, int | None]]]:
    """One snapshot contract as an openCost element, plus how each of its invoices fared.

    ``invoice_outcomes`` covers every invoice row of the contract as
    ``(row, exported, had_errors, xml_index)``; a contract that gives up before reaching
    its invoices leaves those rows carrying the exclusion instead.
    """
    invoice_outcomes: list[tuple[Any, bool, bool, int | None]] = []

    institution = _institution_of(report_contract)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        _record_issue(issues, _create_global_warning(report_contract, NO_INSTITUTION_MESSAGE))
        # The walk below never runs; every invoice inherits the parent's exclusion.
        invoice_outcomes.extend((row, False, True, None) for row in report_contract.invoices.all())
        return None, invoice_outcomes

    participation = _get_participation(
        report_contract.participation_from, report_contract.participation_to
    )
    if participation is None:
        # XSD requires the participation block with both dates.
        _record_issue(issues, _create_warning(report_contract, NO_PARTICIPATION_MESSAGE))
        invoice_outcomes.extend((row, False, True, None) for row in report_contract.invoices.all())
        return None, invoice_outcomes

    contract_secondary_identifiers = _get_contract_secondary_identifiers(
        (
            identifier.identifier_type,
            identifier.value,
        )
        for identifier in report_contract.secondary_identifiers.all()
    )

    invoice_exclusions: list[ValidationWarning] = []
    invoice_elements: list[ContractInvoiceType] = []
    for report_invoice in report_contract.invoices.all():
        row_issues: list[ValidationWarning] = []
        invoice = _contract_invoice(
            report_contract,
            report_invoice,
            report_invoice.positions.all(),
            report_invoice.amount_invoice,
            report_invoice.amount_invoice_currency,
            row_issues,
        )
        if invoice is None:
            invoice_outcomes.append((report_invoice, False, True, None))
        else:
            invoice_elements.append(invoice)
            invoice_outcomes.append(
                (
                    report_invoice,
                    True,
                    any(warning.level == "error" for warning in row_issues),
                    len(invoice_elements) - 1,
                )
            )
        invoice_exclusions.extend(row_issues)

    cost_data = _get_contract_cost_data(report_contract, invoice_elements)
    if cost_data is None:
        # XSD requires at least one invoice_group — without cost data
        # we cannot produce a valid record.
        _record_issue(
            issues,
            _create_warning(
                report_contract,
                _entity_exclusion([w.message for w in invoice_exclusions]),
            ),
        )
        # The built elements never reach the document; their rows are not exported either.
        invoice_outcomes = [
            (row, False, True, None) for row, _exported, _errors, _index in invoice_outcomes
        ]
        return None, invoice_outcomes

    issues.extend(invoice_exclusions)

    if not report_contract.primary_identifier_value:
        # ESAC is mandatory in the schema, so the contract is exported
        # with the placeholder value instead of a real identifier.
        _record_issue(
            issues, _create_warning(report_contract, NO_ESAC_MESSAGE, level="warning")
        )

    primary_identifier = ContractPrimaryIdentifier(
        value=report_contract.primary_identifier_value or UNKNOWN_ESAC,
        type=ContractPrimaryIdentifierType.ESAC,
    )

    return (
        ContractType(
            contract_name=report_contract.contract_name,
            institution=institution,
            participation=participation,
            primary_identifier=primary_identifier,
            secondary_identifiers=contract_secondary_identifiers,
            cost_data=cost_data,
        ),
        invoice_outcomes,
    )


# --- the backfill ------------------------------------------------------------------------


def _esac_values_by_contract(apps: Any, publications: Sequence[Any]) -> dict[int, str]:
    """Each contract's ESAC identifier, read live as the original transform read it.

    ``part_of_contract`` names its contract through the live link, which is not part of the
    snapshot; the first ESAC link wins, the same first the original read answered with.
    """
    contract_ids = {
        linked_contract.contract_id
        for publication in publications
        for linked_contract in publication.linked_contracts.all()
    }
    if not contract_ids:
        return {}

    contract_link = apps.get_model("contracts", "ContractLink")
    values: dict[int, str] = {}
    for link in contract_link.objects.filter(contract__in=contract_ids).select_related("type"):
        if link.type.name == "ESAC":
            values.setdefault(link.contract_id, link.value)

    return values


def _load_publications(apps: Any, report: Any) -> list[Any]:
    """The report's publication rows with their snapshot children, in read order.

    Invoice positions carry no explicit order: their ``Meta`` sort (amount) is the sort the
    original transform ran with, and an unsorted tie stays in the order that sort left it -
    pinning a second key here would reshuffle exactly the rows the stored document must not
    move. A publication-contract link tie gets the row first attached, the one the
    original's own attachment order put first.
    """
    report_publication = apps.get_model("opencost", "OpenCostReportPublication")
    report_publication_contract = apps.get_model("opencost", "OpenCostReportPublicationContract")
    report_invoice = apps.get_model("opencost", "OpenCostReportInvoice")

    return list(
        report_publication.objects.filter(report=report)
        .order_by("id")
        .prefetch_related(
            "institution_identifiers",
            "links",
            Prefetch(
                "linked_contracts",
                queryset=report_publication_contract.objects.order_by("contract_year", "id"),
            ),
            Prefetch("invoices", queryset=report_invoice.objects.order_by("id")),
        )
        .prefetch_related("invoices__positions")
    )


def _load_contracts(apps: Any, report: Any) -> list[Any]:
    """The report's contract rows with their snapshot children, in read order."""
    report_contract = apps.get_model("opencost", "OpenCostReportContract")
    report_contract_invoice = apps.get_model("opencost", "OpenCostReportContractInvoice")

    return list(
        report_contract.objects.filter(report=report)
        .order_by("id")
        .prefetch_related(
            "institution_identifiers",
            "secondary_identifiers",
            Prefetch("invoices", queryset=report_contract_invoice.objects.order_by("id")),
        )
        .prefetch_related("invoices__positions")
    )


def _store_item_outcomes(
    rows: Sequence[Any], outcomes: Sequence[tuple[bool, bool, int | None]]
) -> None:
    """Write exported/had_errors/ordinal onto item rows, positionally."""
    if not rows:
        return

    for row, (exported, had_errors, xml_ordinal) in zip(rows, outcomes, strict=True):
        row.exported = exported
        row.had_errors = had_errors
        row.xml_ordinal = xml_ordinal

    rows[0].__class__.objects.bulk_update(
        list(rows), ["exported", "had_errors", "xml_ordinal"], batch_size=500
    )


def _store_invoice_outcomes(
    invoice_outcomes: Sequence[tuple[Any, bool, bool, int | None]],
) -> None:
    """Write exported/had_errors/index onto invoice rows of one table."""
    if not invoice_outcomes:
        return

    rows = []
    for row, exported, had_errors, xml_index in invoice_outcomes:
        row.exported = exported
        row.had_errors = had_errors
        row.xml_index = xml_index
        rows.append(row)

    rows[0].__class__.objects.bulk_update(
        rows, ["exported", "had_errors", "xml_index"], batch_size=500
    )


def _mark_error_bearers(
    outcomes: Sequence[tuple[bool, bool, int | None]],
    rows: Sequence[Any],
    issues: Sequence[ValidationWarning],
) -> list[tuple[bool, bool, int | None]]:
    """Raise had_errors on exported rows an error-level issue was reported about.

    Issues are attributed by entity: every issue a row caused names that row, whether the
    wording is about the item itself or about one of its invoices. Excluded rows already
    carry the flag - nothing is left out without an error being reported about it - and an
    exclusion said under the "global" heading only ever concerns an excluded row.
    """
    errored = {
        (issue.entity_type, issue.entity_id)
        for issue in issues
        if issue.level == "error"
    }
    marked: list[tuple[bool, bool, int | None]] = []
    for row, (exported, had_errors, xml_ordinal) in zip(rows, outcomes, strict=True):
        if exported:
            entity_type = "publication" if _is_publication_row(row) else "contract"
            entity_id = row.publication_id if entity_type == "publication" else row.contract_id
            had_errors = (entity_type, entity_id) in errored or ("global", entity_id) in errored
        marked.append((exported, had_errors, xml_ordinal))

    return marked


def _backfill_report(apps: Any, report: Any) -> None:
    """One legacy report: its snapshot tree becomes the stored document, issue log and flags."""
    issues: list[ValidationWarning] = []

    publications = _load_publications(apps, report)
    contracts = _load_contracts(apps, report)
    esac_values = _esac_values_by_contract(apps, publications)

    publication_elements: list[PublicationType] = []
    publication_outcomes: list[tuple[bool, bool, int | None]] = []
    publication_invoice_outcomes: list[tuple[Any, bool, bool, int | None]] = []
    for row in publications:
        element, invoice_outcomes = _publication_element(row, issues, esac_values)
        publication_invoice_outcomes.extend(invoice_outcomes)
        if element is None:
            publication_outcomes.append((False, True, None))
            continue

        publication_elements.append(element)
        publication_outcomes.append((True, False, len(publication_elements) - 1))

    contract_elements: list[ContractType] = []
    contract_outcomes: list[tuple[bool, bool, int | None]] = []
    contract_invoice_outcomes: list[tuple[Any, bool, bool, int | None]] = []
    for row in contracts:
        element, invoice_outcomes = _contract_element(row, issues)
        contract_invoice_outcomes.extend(invoice_outcomes)
        if element is None:
            contract_outcomes.append((False, True, None))
            continue

        contract_elements.append(element)
        contract_outcomes.append((True, False, len(contract_elements) - 1))

    # An exported row's own had_errors flag says whether the document holds it whole: an
    # error-level issue reported about a row - including one about a row's invoice - means
    # the stored document is incomplete for it. Warnings alone keep a row clean.
    publication_outcomes = _mark_error_bearers(publication_outcomes, publications, issues)
    contract_outcomes = _mark_error_bearers(contract_outcomes, contracts, issues)

    if not publication_elements and not contract_elements:
        # OpenCost requires at least one publication or contract.
        xml_content = ""
    else:
        xml_content = opencost.to_xml(
            Data(
                publication=publication_elements if publication_elements else None,
                contract=contract_elements if contract_elements else None,
            )
        )

    report.xml_content = xml_content
    report.issues = [asdict(warning) for warning in issues]
    report.errors_count = sum(1 for warning in issues if warning.level == "error")
    report.warnings_count = sum(1 for warning in issues if warning.level == "warning")
    report.save(update_fields=["xml_content", "issues", "errors_count", "warnings_count"])

    _store_item_outcomes(publications, publication_outcomes)
    _store_item_outcomes(contracts, contract_outcomes)
    _store_invoice_outcomes(publication_invoice_outcomes)
    _store_invoice_outcomes(contract_invoice_outcomes)


def backfill_reports(apps: Any, schema_editor: Any) -> None:
    """Give every legacy report the document its snapshot tree describes.

    Each report is written inside its own savepoint: a snapshot that cannot be transformed
    (broken references, data the issue builders cannot resolve) rolls back to exactly the
    empty state it started from - a half-stored document with unset flags is the one outcome
    worse than none, because it reads as complete - logs, and leaves every later report to
    be backfilled. The report stays recoverable through Regenerate.
    """
    report_model = apps.get_model("opencost", "OpenCostReport")

    backfilled = 0
    skipped: list[int] = []
    for report in report_model.objects.filter(xml_content="").order_by("pk"):
        try:
            with transaction.atomic():
                _backfill_report(apps, report)
        except Exception as error:
            skipped.append(report.pk)
            logger.warning("openCost backfill of report %s rolled back: %s", report.pk, error)
            continue

        backfilled += 1

    logger.info(
        "openCost XML backfill complete: %s report(s) filled, %s left empty%s",
        backfilled,
        len(skipped),
        f" (pks {', '.join(str(pk) for pk in skipped)})" if skipped else "",
    )
