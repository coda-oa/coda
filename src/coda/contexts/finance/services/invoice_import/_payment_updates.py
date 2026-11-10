"""Payment status updates for both manual and bulk invoice paths."""

from coda.apps.invoices import repository
from coda.apps.publications.services import publications
from coda.domain.finance.invoice import Invoice
from coda.domain.publication.payment import InvoiceReceived, PaymentEvent, PublicationPaid
from coda.domain.publication.publication import PublicationId


def payment_event_for(invoice: Invoice) -> PaymentEvent:
    if not invoice.id:
        raise ValueError("Invoice must have an ID to create a payment status.")

    if invoice.is_paid():
        return PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)

    return InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)


def update_publication_payment_statuses(invoices: list[Invoice]) -> None:
    payment_updates = [
        (publication_id, payment_event_for(invoice))
        for invoice in invoices
        for publication_id in publication_positions(invoice)
        if invoice.id
    ]

    if payment_updates:
        publications.bulk_update_payments(payment_updates)


def update_single_invoice_payments(invoice: Invoice) -> None:
    update_payments(invoice, payment_event_for(invoice))


def unpay_deleted_publication_positions(invoice: Invoice) -> None:
    if not invoice.id:
        return

    saved_invoice = repository.get_by_id(invoice.id)
    saved_publication_positions = set(publication_positions(saved_invoice))
    new_publication_positions = set(publication_positions(invoice))
    deleted_publication_ids = saved_publication_positions.difference(new_publication_positions)
    for publication in deleted_publication_ids:
        publications.invoice_deleted(publication, invoice.id)


def update_payments(invoice: Invoice, event: PaymentEvent) -> None:
    payment_updates = [(p, event) for p in publication_positions(invoice)]
    if payment_updates:
        publications.bulk_update_payments(payment_updates)


def publication_positions(invoice: Invoice) -> list[PublicationId]:
    return [p.item.item for p in invoice.positions if isinstance(p.item.item, PublicationId)]
