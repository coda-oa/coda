"""The report's items as one openCost document, read from live CODA data.

:func:`transform_report` is the whole entry point. It walks the report's own item rows — the
publications, contracts and invoices it holds — and reads everything the document needs off the
CODA objects those rows point at: titles, links, identifiers, institution hierarchies and invoice
lines, all freshly fetched. What the XSD cannot be given is left out and reported with the same
wording the snapshot transform uses, which the mappers and messages imported below are shared
from.

Membership is never decided here: the rows handed in are the report's item list, and iterating
them in id order is also what fixes the order the document's lists come out in. Every result is
returned as an outcome keyed by the row's entity id (or the invoice row's own id), so ordinals can
never be attributed to the wrong row by an accident of fetch order.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple
from uuid import uuid4

from coda.apps.contracts.models import Contract
from coda.apps.invoices.models import Invoice, Position
from coda.apps.opencost.data_aggregation import (
    HomeInstitutionCache,
    InstitutionHierarchyCache,
    get_institution_data,
)
from coda.apps.opencost.issues import (
    GlobalWarning,
    ValidationWarning,
    create_warning,
    record_issue,
)
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportInvoice,
    OpenCostReportPublication,
)
from coda.apps.opencost.transformers.contract import (
    NO_ESAC_MESSAGE,
    NO_INSTITUTION_MESSAGE,
    NO_PARTICIPATION_MESSAGE,
    UNKNOWN_ESAC,
    get_contract_primary_identifier,
    get_contract_secondary_identifiers,
    get_participation,
    invoices_period_of,
    secondary_identifiers_from_links,
)
from coda.apps.opencost.transformers.entities import entity_exclusion, institution_from
from coda.apps.opencost.transformers.invoices import (
    LiveInvoice,
    LiveInvoicePosition,
    contract_invoice,
    publication_invoice,
)
from coda.apps.opencost.transformers.publication import (
    NO_INSTITUTION_REASON,
    get_publication_type,
    get_secondary_identifiers,
    no_doi_primary_identifier,
    part_of_contract,
)
from coda.apps.publications.models import Publication
from opencost import (
    ContractCostDataType,
    ContractInvoiceGroupType,
    ContractInvoiceType,
    ContractPrimaryIdentifier,
    ContractPrimaryIdentifierType,
    ContractType,
    Data,
    PartOfContractType,
    PublicationCostDataType,
    PublicationInvoiceType,
    PublicationPrimaryIdentifier,
    PublicationType,
)

__all__ = ["LiveTransform", "MissingEntityError", "transform_report"]


class MissingEntityError(Exception):
    """A report row points at a CODA object the caller's fetch did not return.

    Nothing can be said about such a row in the document's own terms, so the run is abandoned
    rather than guessed at; the caller decides what a failed transform is worth.
    """


@dataclass(frozen=True)
class ItemOutcome:
    """How one item row fared: in the document or not, at which position, and how dirty."""

    exported: bool
    had_errors: bool
    xml_ordinal: int | None


@dataclass(frozen=True)
class InvoiceOutcome:
    """How one invoice row fared, indexed within its parent item's exported invoices."""

    exported: bool
    had_errors: bool
    xml_index: int | None


class LiveTransform(NamedTuple):
    """The document, what had to be left out of it, and how every row fared.

    Items are keyed by the CODA entity id their row points at; invoice rows by their own id,
    since one invoice can be an item of several parents.
    """

    data: Data | None
    issues: list[ValidationWarning]
    publications: dict[int, ItemOutcome]
    contracts: dict[int, ItemOutcome]
    publication_invoices: dict[int, InvoiceOutcome]
    contract_invoices: dict[int, InvoiceOutcome]


class PublicationPhase(NamedTuple):
    """The publication document, whose contracts are already fixed."""

    elements: list[PublicationType]
    outcomes: dict[int, ItemOutcome]
    invoice_outcomes: dict[int, InvoiceOutcome]


class ContractPhase(NamedTuple):
    """The contract document plus the group ids its publications have to be linked by."""

    elements: list[ContractType]
    outcomes: dict[int, ItemOutcome]
    invoice_outcomes: dict[int, InvoiceOutcome]
    group_ids: dict[int, str]


def transform_report(
    report: OpenCostReport,
    publications: Sequence[OpenCostReportPublication],
    contracts: Sequence[OpenCostReportContract],
    live_publications: Mapping[int, Publication],
    live_contracts: Mapping[int, Contract],
    live_invoices: Mapping[int, Invoice],
    home_institution: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
) -> LiveTransform:
    """The whole item list as one openCost document, plus what had to be left out.

    Contracts are transformed first because a publication's ``part_of_contract`` names its
    contract through the group id this run gave that contract's invoices.
    """
    issues: list[ValidationWarning] = []

    contract_phase = _transform_contracts(
        report, contracts, live_contracts, live_invoices, home_institution, issues
    )
    publication_phase = _transform_publications(
        publications,
        live_publications,
        live_invoices,
        home_institution,
        institution_cache,
        contract_phase.group_ids,
        issues,
    )

    if not publication_phase.elements and not contract_phase.elements:
        # OpenCost requires at least one publication or contract
        data = None
    else:
        data = Data(
            publication=publication_phase.elements or None,
            contract=contract_phase.elements or None,
        )

    return LiveTransform(
        data=data,
        issues=issues,
        publications=publication_phase.outcomes,
        contracts=contract_phase.outcomes,
        publication_invoices=publication_phase.invoice_outcomes,
        contract_invoices=contract_phase.invoice_outcomes,
    )


def _transform_contracts(
    report: OpenCostReport,
    rows: Sequence[OpenCostReportContract],
    live_contracts: Mapping[int, Contract],
    live_invoices: Mapping[int, Invoice],
    home_institution: HomeInstitutionCache,
    issues: list[ValidationWarning],
) -> ContractPhase:
    elements: list[ContractType] = []
    outcomes: dict[int, ItemOutcome] = {}
    invoice_outcomes: dict[int, InvoiceOutcome] = {}
    group_ids: dict[int, str] = {}

    for row in rows:
        contract = _require(live_contracts, row.contract_id, "contract")
        invoice_rows = list(row.invoices.all())
        _left_out(invoice_rows, invoice_outcomes)
        # A group id is only worth publishing once the contract has invoices of its own for a
        # publication's part_of_contract to join.
        group_id = str(uuid4())
        if invoice_rows:
            group_ids[row.contract_id] = group_id

        row_issues: list[ValidationWarning] = []
        element = _contract_element(
            report,
            row,
            contract,
            invoice_rows,
            group_id,
            live_invoices,
            home_institution,
            row_issues,
            invoice_outcomes,
        )
        if element is None:
            outcomes[row.contract_id] = _excluded()
            issues.extend(row_issues)
            continue

        elements.append(element)
        outcomes[row.contract_id] = _exported(row_issues, len(elements) - 1)
        issues.extend(row_issues)

    return ContractPhase(elements, outcomes, invoice_outcomes, group_ids)


def _contract_element(
    report: OpenCostReport,
    row: OpenCostReportContract,
    contract: Contract,
    invoice_rows: Sequence[OpenCostReportContractInvoice],
    group_id: str,
    live_invoices: Mapping[int, Invoice],
    home_institution: HomeInstitutionCache,
    row_issues: list[ValidationWarning],
    invoice_outcomes: dict[int, InvoiceOutcome],
) -> ContractType | None:
    institution = institution_from(home_institution.institution_name, home_institution.identifiers)
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        record_issue(row_issues, GlobalWarning.create(row, NO_INSTITUTION_MESSAGE))
        return None

    participation = get_participation(contract.start_date, contract.end_date)
    if participation is None:
        # XSD requires the participation block with both dates.
        record_issue(row_issues, create_warning(row, NO_PARTICIPATION_MESSAGE))
        return None

    invoice_issues: list[ValidationWarning] = []
    positions = _positions_by_invoice(contract.position_set.all())
    invoice_elements = _contract_invoice_elements(
        row, invoice_rows, positions, live_invoices, invoice_issues, invoice_outcomes
    )
    if not invoice_elements:
        # XSD requires at least one invoice_group — without cost data
        # we cannot produce a valid record.
        record_issue(
            row_issues,
            create_warning(row, entity_exclusion([w.message for w in invoice_issues])),
        )
        return None

    row_issues.extend(invoice_issues)

    primary_identifier_value = get_contract_primary_identifier(contract)
    if not primary_identifier_value:
        # ESAC is mandatory in the schema, so the contract is exported
        # with the placeholder value instead of a real identifier.
        record_issue(row_issues, create_warning(row, NO_ESAC_MESSAGE, level="warning"))

    return ContractType(
        contract_name=contract.name,
        institution=institution,
        participation=participation,
        primary_identifier=ContractPrimaryIdentifier(
            value=primary_identifier_value or UNKNOWN_ESAC,
            type=ContractPrimaryIdentifierType.ESAC,
        ),
        secondary_identifiers=get_contract_secondary_identifiers(
            secondary_identifiers_from_links(contract)
        ),
        cost_data=ContractCostDataType(
            invoice_group=[
                ContractInvoiceGroupType(
                    group_id=group_id,
                    invoices_period=invoices_period_of(report),
                    invoice=invoice_elements,
                )
            ]
        ),
    )


def _contract_invoice_elements(
    report_item: OpenCostReportContract,
    invoice_rows: Sequence[OpenCostReportContractInvoice],
    positions: Mapping[int, list[LiveInvoicePosition]],
    live_invoices: Mapping[int, Invoice],
    invoice_issues: list[ValidationWarning],
    invoice_outcomes: dict[int, InvoiceOutcome],
) -> list[ContractInvoiceType]:
    """The contract's invoice elements, each with the outcome of the row it came from.

    The contract's own positions decide what an invoice is being given: rows on an invoice this
    contract holds none of are said to have nothing reportable, exactly as an invoice collected
    without any would have been.
    """
    elements: list[ContractInvoiceType] = []
    for invoice_row in invoice_rows:
        rows = positions.get(invoice_row.invoice_id, [])
        row_issues: list[ValidationWarning] = []
        element = contract_invoice(
            report_item,
            live_invoice(_require(live_invoices, invoice_row.invoice_id, "invoice")),
            rows,
            *_invoice_total(rows),
            row_issues,
        )
        if element is None:
            invoice_outcomes[invoice_row.id] = _excluded_invoice()
        else:
            elements.append(element)
            invoice_outcomes[invoice_row.id] = InvoiceOutcome(
                True, _has_errors(row_issues), len(elements) - 1
            )
        invoice_issues.extend(row_issues)

    return elements


def _invoice_total(rows: Sequence[LiveInvoicePosition]) -> tuple[Decimal | None, str]:
    """The price stated on an invoice over the positions asked about, and its currency.

    Every row counts, cost types openCost rejects included, since openCost is being told the
    invoice's price and not the sum of its exported items. The currency is the first row's,
    which the position order fixes by amount.
    """
    if not rows:
        return None, ""

    return sum((Decimal(str(row.amount)) for row in rows), Decimal(0)), rows[0].currency


def _transform_publications(
    rows: Sequence[OpenCostReportPublication],
    live_publications: Mapping[int, Publication],
    live_invoices: Mapping[int, Invoice],
    home_institution: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
    group_ids: Mapping[int, str],
    issues: list[ValidationWarning],
) -> PublicationPhase:
    elements: list[PublicationType] = []
    outcomes: dict[int, ItemOutcome] = {}
    invoice_outcomes: dict[int, InvoiceOutcome] = {}

    for row in rows:
        publication = _require(live_publications, row.publication_id, "publication")
        invoice_rows = list(row.invoices.all())
        _left_out(invoice_rows, invoice_outcomes)

        row_issues: list[ValidationWarning] = []
        element = _publication_element(
            row,
            publication,
            invoice_rows,
            live_invoices,
            home_institution,
            institution_cache,
            group_ids,
            row_issues,
            invoice_outcomes,
        )
        if element is None:
            outcomes[row.publication_id] = _excluded()
            issues.extend(row_issues)
            continue

        elements.append(element)
        outcomes[row.publication_id] = _exported(row_issues, len(elements) - 1)
        issues.extend(row_issues)

    return PublicationPhase(elements, outcomes, invoice_outcomes)


def _publication_element(
    row: OpenCostReportPublication,
    publication: Publication,
    invoice_rows: Sequence[OpenCostReportInvoice],
    live_invoices: Mapping[int, Invoice],
    home_institution: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
    group_ids: Mapping[int, str],
    row_issues: list[ValidationWarning],
    invoice_outcomes: dict[int, InvoiceOutcome],
) -> PublicationType | None:
    institution = institution_from(
        *get_institution_data(publication, home_institution, institution_cache)
    )
    if institution is None:
        # XSD requires institution to have at least one name or id.
        # Without institution data we cannot produce a valid record.
        record_issue(
            row_issues,
            GlobalWarning.create(row, entity_exclusion([NO_INSTITUTION_REASON])),
        )
        return None

    invoice_issues: list[ValidationWarning] = []
    positions = _positions_by_invoice(publication.position_set.all())
    invoice_elements = _publication_invoice_elements(
        row, invoice_rows, positions, live_invoices, invoice_issues, invoice_outcomes
    )

    linked_contract = _part_of_contract(publication, group_ids)

    if not invoice_elements and linked_contract is None:
        # XSD requires at least one of invoice or part_of_contract.
        # Without cost data we cannot produce a valid record.
        record_issue(
            row_issues,
            create_warning(row, entity_exclusion([w.message for w in invoice_issues])),
        )
        return None

    row_issues.extend(invoice_issues)

    doi = get_publication_doi(publication)
    if doi:
        primary_identifier = PublicationPrimaryIdentifier(doi=doi)
    else:
        publisher_name, journal_name = get_publisher_and_journal(publication)
        primary_identifier = no_doi_primary_identifier(
            row, publication.title, publisher_name, journal_name, row_issues
        )
    return PublicationType(
        primary_identifier=primary_identifier,
        secondary_identifiers=get_secondary_identifiers(
            get_secondary_identifier_pairs(publication)
        ),
        institution=institution,
        publication_type=get_publication_type(get_publication_type_name(publication)),
        external_costsplitting=get_external_costsplitting(publication),
        cost_data=PublicationCostDataType(
            invoice=invoice_elements or None, part_of_contract=linked_contract
        ),
    )


def _publication_invoice_elements(
    report_item: OpenCostReportPublication,
    invoice_rows: Sequence[OpenCostReportInvoice],
    positions: Mapping[int, list[LiveInvoicePosition]],
    live_invoices: Mapping[int, Invoice],
    invoice_issues: list[ValidationWarning],
    invoice_outcomes: dict[int, InvoiceOutcome],
) -> list[PublicationInvoiceType]:
    """The publication's invoice elements, each with the outcome of the row it came from.

    The publication's own positions decide what an invoice is being given: a row for an invoice
    it holds no positions on has nothing reportable, exactly as one collected without any would
    have had.
    """
    elements: list[PublicationInvoiceType] = []
    for invoice_row in invoice_rows:
        rows = positions.get(invoice_row.invoice_id, [])
        row_issues: list[ValidationWarning] = []
        element = publication_invoice(
            report_item,
            live_invoice(_require(live_invoices, invoice_row.invoice_id, "invoice")),
            rows,
            row_issues,
        )
        if element is None:
            invoice_outcomes[invoice_row.id] = _excluded_invoice()
        else:
            elements.append(element)
            invoice_outcomes[invoice_row.id] = InvoiceOutcome(
                True, _has_errors(row_issues), len(elements) - 1
            )
        invoice_issues.extend(row_issues)

    return elements


def get_publication_doi(publication: Publication) -> str:
    """The publication's DOI among its typed links, empty when it has none."""
    doi_link = next(
        (link for link in publication.links.all() if link.type.name == "DOI"),
        None,
    )
    return doi_link.value if doi_link else ""


def get_publisher_and_journal(publication: Publication) -> tuple[str, str]:
    """The publisher and journal a publication is published by, from its own records."""
    if publication.article_journal:
        return publication.article_journal.publisher.name, publication.article_journal.title

    if publication.monograph_publisher:
        return publication.monograph_publisher.name, ""

    return "", ""


def get_publication_type_name(publication: Publication) -> str:
    return publication.publication_type.name if publication.publication_type else ""


def get_secondary_identifier_pairs(publication: Publication) -> list[tuple[str, str]]:
    """The publication's non-DOI links as ``(type, value)``; the DOI is its own identifier."""
    return [
        (link.type.name.lower(), link.value)
        for link in publication.links.all()
        if link.type.name.lower() != "doi"
    ]


def get_external_costsplitting(publication: Publication) -> bool | None:
    """The cost sharing recorded on the publication's funding request, if it has one."""
    if hasattr(publication, "fundingrequest") and publication.fundingrequest:
        return publication.fundingrequest.external_costsplitting

    return None


def _part_of_contract(
    publication: Publication, group_ids: Mapping[int, str]
) -> PartOfContractType | None:
    """The contract the publication is published under, as openCost names it.

    Of everything the publication is attached to that is the earliest contract year, ties broken
    by the order the attachments were made in; a contract this run holds no invoices for is
    named without a group id, and one with no ESAC cannot be named at all.
    """
    attachments = list(publication.attached_contracts.all())
    if not attachments:
        return None

    attached = min(attachments, key=lambda attachment: (attachment.contract_year, attachment.id))

    return part_of_contract(attached.contract, group_ids.get(attached.contract_id))


def _positions_by_invoice(positions: Iterable[Position]) -> dict[int, list[LiveInvoicePosition]]:
    """Live positions grouped by the invoice they sit on, each group in the fetched order."""
    grouped: dict[int, list[LiveInvoicePosition]] = {}
    for position in positions:
        grouped.setdefault(position.invoice_id, []).append(live_position(position))

    return grouped


def live_position(position: Position) -> LiveInvoicePosition:
    """One CODA position in the shape the invoice rules read.

    The tax amount is the position's own arithmetic, not a stored copy of it.
    """
    return LiveInvoicePosition(
        amount=position.cost_amount,
        currency=position.cost_currency,
        cost_type=position.cost_type,
        vat=Decimal(str(position.cost_amount))
        * (Decimal(str(position.tax_rate)) if position.tax_rate else Decimal(0)),
    )


def live_invoice(invoice: Invoice) -> LiveInvoice:
    """A CODA invoice in the shape the invoice rules read."""
    return LiveInvoice(
        invoice_number=invoice.number or "",
        creditor=invoice.creditor.name if invoice.creditor else "",
        invoice_date=invoice.date,
    )


def _require[T](by_id: Mapping[int, T], entity_id: int, what: str) -> T:
    entity = by_id.get(entity_id)
    if entity is None:
        raise MissingEntityError(f"no {what} {entity_id} was fetched for this report")
    return entity


def _left_out(
    invoice_rows: Sequence[OpenCostReportInvoice] | Sequence[OpenCostReportContractInvoice],
    outcomes: dict[int, InvoiceOutcome],
) -> None:
    """Mark every invoice row of an item as left out, before the item is even attempted.

    An item that gives up on its way to the document - for want of an institution, or of the
    dates its participation is stated in - never reaches its invoices to say what became of them,
    and an outcome they were never given is a row whose state nobody can tell. The invoice
    builders overwrite this for every row they do look at.
    """
    outcomes.update({invoice_row.id: _excluded_invoice() for invoice_row in invoice_rows})


def _excluded_invoice() -> InvoiceOutcome:
    """An invoice row the document does not hold, whether it was the reason or inherited it."""
    return InvoiceOutcome(exported=False, had_errors=True, xml_index=None)


def _excluded() -> ItemOutcome:
    """An item the document does not hold.

    Nothing is left out without an error being reported about it, so an excluded row always
    carries one - even where the wording that explains it is its parent's.
    """
    return ItemOutcome(exported=False, had_errors=True, xml_ordinal=None)


def _exported(row_issues: Sequence[ValidationWarning], xml_ordinal: int) -> ItemOutcome:
    """An item the document holds, at the position it holds it at."""
    return ItemOutcome(exported=True, had_errors=_has_errors(row_issues), xml_ordinal=xml_ordinal)


def _has_errors(issues: Sequence[ValidationWarning]) -> bool:
    """Whether anything reported about a row said it could not be exported cleanly.

    Warnings stay in the issue log alone: only an error says the XML that was written is
    incomplete for this row.
    """
    return any(issue.level == "error" for issue in issues)
