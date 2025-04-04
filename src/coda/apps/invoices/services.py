from coda.apps.invoices import repository
from coda.apps.publications.services import publications
from coda.domain.invoice import Invoice, InvoiceId
from coda.domain.publication.payment import InvoiceReceived, PublicationPaid, PublicationPayment
from coda.domain.publication.publication import PublicationId


def save(invoice: Invoice) -> InvoiceId:
    invoice.id = repository.save(invoice)
    if invoice.is_paid():
        _pay_publications(invoice)
    else:
        _invoice_received(invoice)

    return invoice.id


def pay_invoice(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    invoice.pay()
    repository.save(invoice)
    _pay_publications(invoice)


def reset_payment(invoice_id: InvoiceId) -> None:
    invoice = repository.get_by_id(invoice_id)
    invoice.reset_payment()
    repository.save(invoice)
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
