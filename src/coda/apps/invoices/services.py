from typing import cast
from coda.apps.invoices import repository
from coda.apps.publications.services import publications
from coda.domain.invoice import Invoice, InvoiceId
from coda.domain.publication.payment import InvoiceReceived, PublicationPaid, PublicationPayment
from coda.domain.publication.publication import PublicationId


def save(invoice: Invoice) -> InvoiceId:
    _unpay_deleted_publication_positions(invoice)
    id = _save_invoice(invoice)

    if invoice.is_paid():
        _pay_publications(invoice)
    else:
        _invoice_received(invoice)

    return id


def _unpay_deleted_publication_positions(invoice: Invoice) -> None:
    if not invoice.id:
        return

    try:
        saved_invoice = repository.get_by_id(invoice.id)
    except Exception:
        # Invoice doesn't exist in database yet (e.g., during import with external ID)
        # No need to unpay positions since there are no existing positions to remove
        return
        
    saved_publication_positions = set(_publication_positions(saved_invoice))
    new_publication_positions = set(_publication_positions(invoice))
    deleted_publication_ids = saved_publication_positions.difference(new_publication_positions)
    for publication in deleted_publication_ids:
        _update_or_delete_payment_of_deleted_position(invoice, publication)


def _update_or_delete_payment_of_deleted_position(
    invoice: Invoice, deleted_publication: PublicationId
) -> None:
    other_invoice = repository.get_other_paid_invoice_with_publication(invoice, deleted_publication)

    if other_invoice is None:
        publications.invoice_deleted(deleted_publication)
        return

    publications.update_payment(
        deleted_publication,
        PublicationPaid(
            invoice_id=cast(InvoiceId, other_invoice.id),
            invoice_number=other_invoice.number,
        ),
    )


def _save_invoice(invoice: Invoice) -> InvoiceId:
    if not invoice.id:
        invoice.id = repository.create(invoice)
    else:
        # Check if invoice exists before trying to update
        try:
            existing_invoice = repository.get_by_id(invoice.id)
            repository.update(invoice)
        except Exception:
            # Invoice doesn't exist in database (e.g., import with external ID)
            # Clear the ID and create a new one
            invoice.id = None
            invoice.id = repository.create(invoice)

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
        publications.invoice_deleted(p)

    repository.delete(invoice_id)


def _pay_publications(invoice: Invoice) -> None:
    assert invoice.id is not None, "Only saved invoices can be paid"
    paid = PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)
    _update_payments(invoice, paid)


def _invoice_received(invoice: Invoice) -> None:
    assert invoice.id is not None, "Only saved invoices can be paid"
    invoice_received = InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
    _update_payments(invoice, invoice_received)


def _update_payments(invoice: Invoice, paid: PublicationPayment) -> None:
    for p in _publication_positions(invoice):
        publications.update_payment(p, paid)


def _publication_positions(invoice: Invoice) -> list[PublicationId]:
    return [p.item for p in invoice.positions if isinstance(p.item, PublicationId)]
