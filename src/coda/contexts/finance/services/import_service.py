import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, BinaryIO, TextIO, cast

import pydantic
from django.db.models import Q

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices import repository
from coda.contexts.finance.dto.import_dtos import (
    CommonPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
    InvoiceImportDto,
    PublicationPositionImportDto,
)
from coda.apps.invoices.models import Creditor, FundingSource
from coda.apps.publications.services import publications
from coda.coda_itertools import notnone
from coda.domain import errors
from coda.domain.contract import Contract
from coda.domain.invoice import (
    AnyPosition,
    ContractPosition,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    Position,
    TaxRate,
)
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.payment import InvoiceReceived, PaymentEvent, PublicationPaid
from coda.domain.publication.publication import PublicationId
from coda.domain.string import NonEmptyStr


@dataclass
class InvoiceImportReport:
    valid_invoices: int
    invalid_invoices: int
    errors: dict[str, list[str]]


@dataclass
class RelatedEntityLookups:
    creditor_lookup: dict[str, CreditorId]
    funding_sources_lookup: dict[str, FundingSourceId]
    request_id_lookup: dict[str, PublicationId]
    contract_lookup: dict[str, Contract]


def import_invoices(json_stream: TextIO | BinaryIO) -> InvoiceImportReport:
    text_content = json_stream.read()
    data = json.loads(text_content)

    invoice_dtos, validation_errors = _validate_invoices(data["invoices"])

    if validation_errors:
        _errors = dict(e.unpack() for e in validation_errors)
        return InvoiceImportReport(
            valid_invoices=0,
            invalid_invoices=len(validation_errors),
            errors=_errors,
        )

    processed_invoices, processing_errors = _process_invoices(invoice_dtos)

    return InvoiceImportReport(
        valid_invoices=len(processed_invoices),
        invalid_invoices=len(invoice_dtos) - len(processed_invoices),
        errors=processing_errors,
    )


class InvoiceProcessingError(errors.DomainError):
    def __init__(self, invoice_number: str, reasons: list[str]) -> None:
        super().__init__()
        self.invoice_number = invoice_number
        self.reasons = reasons or []

    def unpack(self) -> tuple[str, list[str]]:
        return self.invoice_number, self.reasons


def _validate_invoice(invoice_number: str, raw_invoice: dict[str, Any]) -> InvoiceImportDto:
    try:
        return InvoiceImportDto.model_validate(raw_invoice)
    except (ValueError, AttributeError) as e:
        raise InvoiceProcessingError(invoice_number, _format_validation_error(e))


def _validate_invoices(
    raw_invoices: list[dict[str, Any]],
) -> tuple[list[InvoiceImportDto], list[InvoiceProcessingError]]:
    """
    Validate a list of raw invoice data and return valid DTOs and validation errors.

    Returns:
        Tuple of (valid_invoice_dtos, validation_errors_by_invoice_number)
    """
    invoice_numbers = _extract_invoice_numbers(raw_invoices)

    with errors.capture(InvoiceProcessingError) as capture:
        invoice_dtos = notnone(
            capture(_validate_invoice, invoice_numbers[i], raw_invoice)
            for i, raw_invoice in enumerate(raw_invoices)
        )

    return list(invoice_dtos), capture.errors


def _extract_invoice_numbers(raw_invoices: list[dict[str, Any]]) -> list[str]:
    """Extract invoice numbers from raw JSON data, providing fallbacks for missing numbers."""
    return [
        raw_invoice.get("number", f"<unknown-{i}>") for i, raw_invoice in enumerate(raw_invoices)
    ]


def _format_validation_error(error: Exception) -> list[str]:
    """Format validation errors into a consistent list of string messages."""
    if isinstance(error, pydantic.ValidationError):
        return [str(err) for err in error.errors()]
    else:
        # Handle other validation-related exceptions
        return [str(error)]


def _process_invoices(
    invoice_dtos: list[InvoiceImportDto],
) -> tuple[list[Invoice], dict[str, list[str]]]:
    """
    Process validated invoice DTOs into domain objects and persist them.

    Returns:
        Tuple of (created_invoices, processing_errors_by_invoice_number)
    """
    request_id_lookup, invoices_with_missing_publications = _find_publication_ids(invoice_dtos)

    valid_invoice_dtos = [
        invoice_dto
        for invoice_dto in invoice_dtos
        if invoice_dto.number not in invoices_with_missing_publications
    ]

    if not valid_invoice_dtos:
        return [], _build_missing_publication_errors(
            invoice_dtos, invoices_with_missing_publications
        )

    lookups = _build_entity_lookups(valid_invoice_dtos, request_id_lookup)
    invoices = _create_invoices(valid_invoice_dtos, lookups)

    invoice_ids = repository.bulk_create(invoices)
    _assign_invoice_ids(invoices, invoice_ids)
    _update_publication_payment_statuses(invoices)

    processing_errors = _build_missing_publication_errors(
        invoice_dtos, invoices_with_missing_publications
    )

    return invoices, processing_errors


def _assign_invoice_ids(invoices: list[Invoice], invoice_ids: list[InvoiceId]) -> None:
    for invoice, invoice_id in zip(invoices, invoice_ids):
        invoice.id = invoice_id


def _build_entity_lookups(
    invoice_dtos: list[InvoiceImportDto], request_id_lookup: dict[str, PublicationId]
) -> RelatedEntityLookups:
    """Build all necessary entity lookups for invoice processing."""
    return RelatedEntityLookups(
        creditor_lookup=_bulk_create_creditors(_creditors(invoice_dtos)),
        funding_sources_lookup=_bulk_create_funding_sources(_funding_sources(invoice_dtos)),
        request_id_lookup=request_id_lookup,
        contract_lookup=_find_contracts(_contracts(invoice_dtos)),
    )


def _create_invoices(
    invoice_dtos: list[InvoiceImportDto], lookups: RelatedEntityLookups
) -> list[Invoice]:
    """Create domain invoice objects from DTOs and lookups."""
    positions_lookup = _build_positions_lookup(invoice_dtos, lookups)

    return [
        _new_invoice(
            invoice_dto,
            lookups.creditor_lookup[invoice_dto.creditor],
            positions_lookup[_invoice_key(invoice_dto)],
        )
        for invoice_dto in invoice_dtos
    ]


def _build_missing_publication_errors(
    all_invoice_dtos: list[InvoiceImportDto], invoices_with_missing_publications: set[str]
) -> dict[str, list[str]]:
    """Build error dictionary for invoices with missing publications."""
    return {
        invoice_dto.number: ["Invoice contains position with non-existing publication"]
        for invoice_dto in all_invoice_dtos
        if invoice_dto.number in invoices_with_missing_publications
    }


def _creditors(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (invoice_dto.creditor for invoice_dto in invoice_dtos if invoice_dto.creditor)


def _contracts(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (
        position.contract_name
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        if isinstance(position, ContractPositionImportDto)
    )


def _funding_sources(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (
        position.funding_source
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
    )


def _build_positions_lookup(
    invoice_dtos: list[InvoiceImportDto], lookups: RelatedEntityLookups
) -> dict[str, list[AnyPosition]]:
    return {
        _invoice_key(invoice_dto): [
            _parse_into_position(p, Currency.from_code(invoice_dto.currency), lookups)
            for p in invoice_dto.positions
        ]
        for invoice_dto in invoice_dtos
    }


def _parse_into_position(
    p: CommonPositionImportDto, currency: Currency, lookups: RelatedEntityLookups
) -> AnyPosition:
    cost = Money(p.amount, currency)
    tax_rate = TaxRate.from_percentage(p.tax_rate)
    funding_source = lookups.funding_sources_lookup[p.funding_source] if p.funding_source else None
    external_id = p.external_id
    position: AnyPosition
    match p:
        case PublicationPositionImportDto():
            id_type = cast(str, p.request_id or p.legacy_request_id)
            position = Position(
                item=lookups.request_id_lookup[id_type],
                cost=cost,
                tax_rate=tax_rate,
                funding_source=funding_source,
                external_position_id=external_id,
                cost_type=p.cost_type,
            )
        case ContractPositionImportDto():
            position = ContractPosition(
                item=lookups.contract_lookup[p.contract_name].in_year(p.contract_year),
                cost=cost,
                tax_rate=tax_rate,
                funding_source=funding_source,
                external_position_id=external_id,
                cost_type=p.cost_type,
            )
        case FreePositionImportDto():
            position = Position(
                item=p.description,
                cost=cost,
                tax_rate=tax_rate,
                funding_source=funding_source,
                external_position_id=external_id,
                cost_type=p.cost_type,
            )
        case _:
            raise ValueError(f"Unknown position type: {p.type}.\n{p}")

    return position


def _invoice_key(invoice_dto: InvoiceImportDto) -> str:
    return str(hash(invoice_dto.model_dump_json()))


def _new_invoice(
    invoice_dto: InvoiceImportDto,
    creditor: CreditorId,
    positions: list[AnyPosition],
) -> Invoice:
    invoice = Invoice.new(
        number=invoice_dto.number,
        date=invoice_dto.date,
        creditor=creditor,
        status=invoice_dto.status,
        external_invoice_id=invoice_dto.external_id,
        comment=invoice_dto.comment,
        positions=positions,
    )

    if invoice_dto.conversion:
        invoice.add_conversion(
            invoice_dto.conversion.exchange_rate,
            Currency.from_code(invoice_dto.conversion.target_currency),
        )

    return invoice


def _find_publication_ids(
    invoices: Iterable[InvoiceImportDto],
) -> tuple[dict[str, PublicationId], set[str]]:
    invoices_with_publications = [
        (invoice_dto.number, cast(str, position.request_id or position.legacy_request_id))
        for invoice_dto in invoices
        for position in invoice_dto.positions
        if isinstance(position, PublicationPositionImportDto)
    ]

    publication_ids = {publication for _, publication in invoices_with_publications}

    requests = FundingRequest.objects.filter(
        Q(request_id__in=publication_ids) | Q(legacy_request_id__in=publication_ids)
    ).prefetch_related("publication")

    invoices_with_missing_publications = {
        invoice_number
        for invoice_number, publication in invoices_with_publications
        if requests.filter(Q(request_id=publication) | Q(legacy_request_id=publication)).count()
        == 0
    }

    return {req.request_id: PublicationId(req.publication.id) for req in requests} | {
        req.legacy_request_id: PublicationId(req.publication.id)
        for req in requests
        if req.legacy_request_id
    }, invoices_with_missing_publications


def _find_contracts(contracts: Iterable[str]) -> dict[str, Contract]:
    contracts = set(contracts)
    existing = contract_repository.find_all_by_names(contracts)
    existing_map: dict[str, Contract] = {c.name: c for c in existing}
    to_create = [
        Contract.new(name=NonEmptyStr(name)) for name in contracts if name not in existing_map
    ]
    if to_create:
        created = contract_repository.create_many(to_create)
        existing_map.update({c.name: c for c in created})
    return {name: existing_map[name] for name in contracts}


def _bulk_create_creditors(creditors: Iterable[str]) -> dict[str, CreditorId]:
    creditors = set(creditors)
    existing = Creditor.objects.filter(name__in=creditors)
    existing_map = {c.name: c for c in existing}
    to_create = [Creditor(name=name) for name in creditors if name not in existing_map]
    if to_create:
        created = Creditor.objects.bulk_create(to_create)
        existing_map.update({c.name: c for c in created})
    return {name: CreditorId(existing_map[name].pk) for name in creditors}


def _bulk_create_funding_sources(funding_sources: Iterable[str]) -> dict[str, FundingSourceId]:
    funding_sources = set(funding_sources)
    existing = FundingSource.objects.filter(name__in=funding_sources)
    existing_map = {fs.name: FundingSourceId(fs.pk) for fs in existing}
    to_create = [FundingSource(name=name) for name in funding_sources if name not in existing_map]
    if to_create:
        created = FundingSource.objects.bulk_create(to_create)
        existing_map.update({fs.name: FundingSourceId(fs.pk) for fs in created})

    return existing_map


def _update_publication_payment_statuses(invoices: list[Invoice]) -> None:
    """
    Update funding request payment statuses based on imported invoice payment statuses.
    This uses bulk operations for optimal performance during large imports.
    """
    payment_updates = [
        (publication_id, _create_payment(invoice))
        for invoice in invoices
        for publication_id in _publication_positions(invoice)
        if invoice.id
    ]

    if payment_updates:
        publications.bulk_update_payments(payment_updates)


def _publication_positions(invoice: Invoice) -> list[PublicationId]:
    return [p.item for p in invoice.positions if isinstance(p.item, PublicationId)]


def _create_payment(invoice: Invoice) -> PaymentEvent:
    if not invoice.id:
        raise ValueError("Invoice must have an ID to create a payment status.")

    if invoice.is_paid():
        return PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)

    return InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
