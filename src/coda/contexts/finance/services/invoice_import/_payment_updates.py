"""Payment status updates for both manual and bulk invoice paths."""

from coda.apps.invoices import repository
from coda.apps.publications.services import publications
from coda.domain.finance.invoice import Invoice
from coda.domain.publication.payment import InvoiceReceived, PaymentEvent, PublicationPaid
from coda.domain.publication.publication import PublicationId


def update_publication_payment_statuses(invoices: list[Invoice]) -> None:
    payment_updates = [
        (publication_id, _create_payment(invoice))
        for invoice in invoices
        for publication_id in _publication_positions(invoice)
        if invoice.id
    ]

    if payment_updates:
        publications.bulk_update_payments(payment_updates)


def update_single_invoice_payments(invoice: Invoice) -> None:
    _unpay_deleted_publication_positions(invoice)

    if invoice.is_paid():
        _pay_publications(invoice)
    else:
        _invoice_received(invoice)


def _unpay_deleted_publication_positions(invoice: Invoice) -> None:
    if not invoice.id:
        return

    saved_invoice = repository.get_by_id(invoice.id)
    saved_publication_positions = set(_publication_positions(saved_invoice))
    new_publication_positions = set(_publication_positions(invoice))
    deleted_publication_ids = saved_publication_positions.difference(new_publication_positions)
    for publication in deleted_publication_ids:
        publications.invoice_deleted(publication, invoice.id)


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
    return [p.item.item for p in invoice.positions if isinstance(p.item.item, PublicationId)]


def _create_payment(invoice: Invoice) -> PaymentEvent:
    if not invoice.id:
        raise ValueError("Invoice must have an ID to create a payment status.")

    if invoice.is_paid():
        return PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)

    return InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
