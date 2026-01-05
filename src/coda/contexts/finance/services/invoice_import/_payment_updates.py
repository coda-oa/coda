"""Private module for handling payment status updates during invoice import."""

from coda.apps.publications.services import publications
from coda.domain.finance.invoice import Invoice
from coda.domain.publication.payment import InvoiceReceived, PaymentEvent, PublicationPaid
from coda.domain.publication.publication import PublicationId


def update_publication_payment_statuses(invoices: list[Invoice]) -> None:
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
    return [p.item.item for p in invoice.positions if isinstance(p.item.item, PublicationId)]


def _create_payment(invoice: Invoice) -> PaymentEvent:
    if not invoice.id:
        raise ValueError("Invoice must have an ID to create a payment status.")

    if invoice.is_paid():
        return PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)

    return InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
