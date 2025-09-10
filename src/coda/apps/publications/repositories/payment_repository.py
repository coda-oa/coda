from typing import Final

from django.db import transaction
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


def bulk_save_payments(payment_updates: list[tuple[PublicationId, PublicationPayment]]) -> None:
    """
    Bulk update publication payment statuses for better performance during imports.

    Args:
        payment_updates: List of (publication_id, payment_status) tuples
    """
    if not payment_updates:
        return

    with transaction.atomic():
        # Group by payment type for efficient processing
        paid_updates = []
        received_updates = []

        for publication_id, payment in payment_updates:
            if isinstance(payment, PublicationPaid):
                paid_updates.append((publication_id, payment))
            elif isinstance(payment, InvoiceReceived):
                received_updates.append((publication_id, payment))

        # Process paid publications
        if paid_updates:
            _bulk_update_payment_status(paid_updates, "paid")  # type: ignore[arg-type]

        # Process invoice received publications
        if received_updates:
            _bulk_update_payment_status(received_updates, "invoice_received")  # type: ignore[arg-type]


def _bulk_update_payment_status(
    updates: list[tuple[PublicationId, InvoiceReceived | PublicationPaid]], status: str
) -> None:
    """Helper function to bulk update payments with the same status."""
    publication_ids = [pub_id for pub_id, _ in updates]

    # Get or create payment records
    existing_payments = {
        p.publication_id: p
        for p in PublicationPaymentModel.objects.filter(publication_id__in=publication_ids)
    }

    payments_to_create = []
    payments_to_update = []

    for publication_id, payment in updates:
        invoice_id = None
        if isinstance(payment, (PublicationPaid, InvoiceReceived)):
            invoice_id = payment.invoice_id

        if publication_id in existing_payments:
            # Update existing
            model = existing_payments[publication_id]
            model.status = status
            model.invoice_id = invoice_id
            payments_to_update.append(model)
        else:
            # Create new
            payments_to_create.append(
                PublicationPaymentModel(
                    publication_id=publication_id, status=status, invoice_id=invoice_id
                )
            )

    # Bulk operations
    if payments_to_create:
        PublicationPaymentModel.objects.bulk_create(payments_to_create)

    if payments_to_update:
        PublicationPaymentModel.objects.bulk_update(
            payments_to_update, fields=["status", "invoice_id"]
        )
