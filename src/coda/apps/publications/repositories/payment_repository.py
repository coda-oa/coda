from typing import Final

from django.db import transaction

from coda.apps.publications.models import PublicationPayment as PublicationPaymentModel
from coda.domain.finance.invoice import InvoiceId
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import (
    InvoicePaymentReset,
    InvoiceReceived,
    PaymentEvent,
    PublicationPaid,
    PublicationPayments,
)


def _to_invoice_received(model: PublicationPaymentModel) -> PaymentEvent:
    assert model.invoice is not None
    return InvoiceReceived(
        invoice_id=InvoiceId(model.invoice.id), invoice_number=model.invoice.number
    )


def _to_publication_paid(model: PublicationPaymentModel) -> PaymentEvent:
    assert model.invoice is not None
    return PublicationPaid(
        invoice_id=InvoiceId(model.invoice.id), invoice_number=model.invoice.number
    )


STATUS_MAPPING: Final = {
    InvoiceReceived: "invoice_received",
    InvoicePaymentReset: "invoice_received",
    PublicationPaid: "paid",
}

REVERSE_STATUS_MAPPING: Final = {
    "invoice_received": _to_invoice_received,
    "paid": _to_publication_paid,
}


def save_payment(publication: PublicationId, publication_payment: PaymentEvent) -> None:
    payments = PublicationPaymentModel.objects.filter(
        publication_id=publication.pk,
        invoice_id=publication_payment.invoice_id.pk,
    ).first()

    if not payments:
        payments = PublicationPaymentModel(
            publication_id=publication.pk, invoice_id=publication_payment.invoice_id.pk
        )

    payments.status = STATUS_MAPPING[type(publication_payment)]
    payments.save()


def delete_payment(publication: PublicationId, invoice_id: InvoiceId) -> None:
    PublicationPaymentModel.objects.filter(
        publication_id=publication.pk,
        invoice_id=invoice_id.pk,
    ).delete()


def find_payment(publication: PublicationId) -> PublicationPayments | None:
    queryset = PublicationPaymentModel.objects.filter(publication_id=publication.pk)
    if queryset.count() == 0:
        return None

    payments = PublicationPayments(publication)
    for model in queryset:
        if model.invoice is None:
            raise ValueError("Payment record has no associated invoice")

        if model.status == "paid":
            payments.paid_invoice(InvoiceId(model.invoice.id), model.invoice.number)
        elif model.status == "invoice_received":
            payments.received_invoice(InvoiceId(model.invoice.id), model.invoice.number)

    return payments


def find_payments(publication_ids: list[PublicationId]) -> dict[PublicationId, PublicationPayments]:
    """Bulk fetch payments for multiple publications.

    Uses select_related('invoice') to fetch invoice details.
    """
    payment_models = PublicationPaymentModel.objects.filter(
        publication_id__in=publication_ids
    ).select_related("invoice")

    result: dict[PublicationId, PublicationPayments] = {}

    for pm in payment_models:
        pub_id = PublicationId(pm.publication_id)

        if pub_id not in result:
            result[pub_id] = PublicationPayments(pub_id)

        payments = result[pub_id]

        if pm.invoice is None:
            raise ValueError("Payment record has no associated invoice")

        invoice_id = InvoiceId(pm.invoice.id)
        invoice_number = pm.invoice.number

        if pm.status == "paid":
            payments.paid_invoice(invoice_id, invoice_number)
        elif pm.status == "invoice_received":
            payments.received_invoice(invoice_id, invoice_number)

    return result


def bulk_save_payments(payment_updates: list[tuple[PublicationId, PaymentEvent]]) -> None:
    """
    Bulk update publication payment statuses for better performance during imports.

    Args:
        payment_updates: List of (publication_id, payment_status) tuples
    """
    if not payment_updates:
        return

    with transaction.atomic():
        paid_updates: list[tuple[PublicationId, PaymentEvent]] = []
        received_updates: list[tuple[PublicationId, PaymentEvent]] = []

        for publication_id, payment in payment_updates:
            if isinstance(payment, PublicationPaid):
                paid_updates.append((publication_id, payment))
            elif isinstance(payment, InvoiceReceived):
                received_updates.append((publication_id, payment))

        if paid_updates:
            _bulk_update_payment_status(paid_updates, "paid")

        if received_updates:
            _bulk_update_payment_status(received_updates, "invoice_received")


def _bulk_update_payment_status(
    updates: list[tuple[PublicationId, PaymentEvent]], status: str
) -> None:
    """Helper function to bulk update payments with the same status."""
    publication_ids = [pub_id for pub_id, _ in updates]

    existing_payments = {
        p.publication_id: p
        for p in PublicationPaymentModel.objects.filter(publication_id__in=publication_ids)
    }

    payments_to_create = []
    payments_to_update = []

    for publication_id, payment in updates:
        invoice_id = payment.invoice_id

        if publication_id in existing_payments:
            model = existing_payments[publication_id.pk]
            model.status = status
            model.invoice_id = invoice_id.pk
            payments_to_update.append(model)
        else:
            payments_to_create.append(
                PublicationPaymentModel(
                    publication_id=publication_id.pk, status=status, invoice_id=invoice_id.pk
                )
            )

    if payments_to_create:
        PublicationPaymentModel.objects.bulk_create(payments_to_create)

    if payments_to_update:
        PublicationPaymentModel.objects.bulk_update(
            payments_to_update, fields=["status", "invoice_id"]
        )
