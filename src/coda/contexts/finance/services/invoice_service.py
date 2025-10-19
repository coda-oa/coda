from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Any

from coda.apps.invoices import repository
from coda.apps.invoices.views.position_dtos.edit_position_dtos import AnyPositionDto
from coda.apps.publications.services import publications
from coda.contexts.finance.dto.invoice_head_dto import InvoiceHeadDto
from coda.domain import errors
from coda.domain.invoice import CreditorId, Invoice, InvoiceId
from coda.domain.money import Currency
from coda.domain.publication.payment import InvoiceReceived, PaymentEvent, PublicationPaid
from coda.domain.publication.publication import PublicationId


def save(invoice: Invoice) -> InvoiceId:
    _unpay_deleted_publication_positions(invoice)
    id = _save_invoice(invoice)

    if invoice.is_paid():
        _pay_publications(invoice)
    else:
        _invoice_received(invoice)

    return id


def parse_invoice(invoice_head: InvoiceHeadDto, positions: list[AnyPositionDto]) -> Invoice:
    currency = invoice_head.currency
    with errors.capture(ValueError) as capture:
        parsed_positions = errors.results(
            capture(p.to_position, currency).map_err(PositionParseError, p) for p in positions
        )

    if parsed_positions.has_errors():
        raise InvoiceParseError(parsed_positions.errors())

    invoice = Invoice.new(
        **invoice_head.model_dump(exclude={"currency"}),
        positions=parsed_positions.values(),
    )

    return invoice


@dataclass
class InvoiceTotal:
    net: Decimal
    tax: Decimal
    total: Decimal


def invoice_total(positions: list[AnyPositionDto], currency: Currency) -> InvoiceTotal:
    parsed = [p.to_position(currency, parse_safe=True) for p in positions]
    invoice = Invoice.new("", datetime.date.today(), CreditorId(0), parsed)

    return InvoiceTotal(
        net=invoice.net().amount,
        tax=invoice.tax().amount,
        total=invoice.total().amount,
    )


def _unpay_deleted_publication_positions(invoice: Invoice) -> None:
    if not invoice.id:
        return

    saved_invoice = repository.get_by_id(invoice.id)
    saved_publication_positions = set(_publication_positions(saved_invoice))
    new_publication_positions = set(_publication_positions(invoice))
    deleted_publication_ids = saved_publication_positions.difference(new_publication_positions)
    for publication in deleted_publication_ids:
        publications.invoice_deleted(publication, invoice.id)


def _save_invoice(invoice: Invoice) -> InvoiceId:
    if not invoice.id:
        invoice.id = repository.create(invoice)
    else:
        repository.update(invoice)

    return invoice.id


def pay_invoice(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    invoice.pay()
    repository.update(invoice)
    _pay_publications(invoice)


def reset_payment(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    invoice.reset_payment()
    repository.update(invoice)
    _invoice_received(invoice)


def delete_invoice(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    for p in _publication_positions(invoice):
        publications.invoice_deleted(p, invoice_id)

    repository.delete(invoice_id)


def _pay_publications(invoice: Invoice) -> None:
    assert invoice.id is not None, "Only saved invoices can be paid"
    paid = PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)
    _update_payments(invoice, paid)


def _invoice_received(invoice: Invoice) -> None:
    assert invoice.id is not None, "Only saved invoices can be paid"
    invoice_received = InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
    _update_payments(invoice, invoice_received)


def _update_payments(invoice: Invoice, paid: PaymentEvent) -> None:
    for p in _publication_positions(invoice):
        publications.update_payment(p, paid)


def _publication_positions(invoice: Invoice) -> list[PublicationId]:
    return [p.item for p in invoice.positions if isinstance(p.item, PublicationId)]


class PositionParseError(Exception):
    def __init__(self, inner: Exception, position: AnyPositionDto, *args: Any) -> None:
        super().__init__(*args)
        self.position = position
        self.inner = inner

    def message(self) -> str:
        return str(self.inner)


class InvoiceParseError(RuntimeError):
    def __init__(self, position_errors: list[PositionParseError]) -> None:
        super().__init__()
        self.position_errors = position_errors

    def error_for(self, position: AnyPositionDto) -> PositionParseError | None:
        for err in self.position_errors:
            if position == err.position:
                return err
        return None
