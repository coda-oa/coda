from typing import Final

from coda.apps.publications.models import PublicationPayment as PublicationPaymentModel
from coda.domain.invoice import InvoiceId
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import InvoiceReceived, PublicationPaid, PublicationPayment


def _to_invoice_received(model: PublicationPaymentModel) -> PublicationPayment:
    assert model.invoice is not None
    return InvoiceReceived(
        invoice_id=InvoiceId(model.invoice.id), invoice_number=model.invoice.number
    )


def _to_publication_paid(model: PublicationPaymentModel) -> PublicationPayment:
    assert model.invoice is not None
    return PublicationPaid(
        invoice_id=InvoiceId(model.invoice.id), invoice_number=model.invoice.number
    )


STATUS_MAPPING: Final = {
    InvoiceReceived: "invoice_received",
    PublicationPaid: "paid",
}

REVERSE_STATUS_MAPPING: Final = {
    "invoice_received": _to_invoice_received,
    "paid": _to_publication_paid,
}


def save_payment(publication: PublicationId, publication_payment: PublicationPayment) -> None:
    model, _ = PublicationPaymentModel.objects.get_or_create(publication_id=publication)
    model.status = STATUS_MAPPING[type(publication_payment)]
    match publication_payment:
        case PublicationPaid(invoice_id, _) | InvoiceReceived(invoice_id, _):
            model.invoice_id = invoice_id

    model.save()


def delete_payment(publication: PublicationId) -> None:
    PublicationPaymentModel.objects.filter(publication_id=publication).delete()


def find_payment(publication: PublicationId) -> PublicationPayment | None:
    model = PublicationPaymentModel.objects.filter(publication_id=publication).first()
    if model is None:
        return None

    assert model.invoice is not None
    return REVERSE_STATUS_MAPPING[model.status](model)
