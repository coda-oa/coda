from coda.domain.invoice import InvoiceId
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import (
    IndividualBillingPaymentStatus,
    Payment,
    IndividualPublicationPaymentStatus,
)


def make_sut() -> IndividualBillingPaymentStatus:
    return IndividualBillingPaymentStatus(publication_id=PublicationId(1))


def test__publication_payment_status__without_payments__is_unpaid() -> None:
    sut = make_sut()

    assert sut.status() == IndividualPublicationPaymentStatus.Unpaid
    assert sut.payments() == []


def test__publication_payment_status__add_invoice_received__is_unpaid_with_pending_payment() -> (
    None
):
    sut = make_sut()

    sut.received_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")

    assert sut.status() == IndividualPublicationPaymentStatus.Unpaid
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=True)
    ]


def test__publication_payment_status__add_paid__is_paid() -> None:
    sut = make_sut()

    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")

    assert sut.status() == IndividualPublicationPaymentStatus.Paid
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=False)
    ]


def test__payment_status_with_pending_payment__add_paid_for_same_invoice__is_paid_with_only_single_payment() -> (
    None
):
    sut = make_sut()

    sut.received_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")

    assert sut.status() == IndividualPublicationPaymentStatus.Paid
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=False)
    ]


def test__payment_status_with_pending_and_paid_payments_of_different_invoices__is_partially_paid() -> (
    None
):
    sut = make_sut()

    sut.received_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.paid_invoice(invoice_id=InvoiceId(2), invoice_number="INV-002")

    assert sut.status() == IndividualPublicationPaymentStatus.PartiallyPaid
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=True),
        Payment(invoice_id=InvoiceId(2), invoice_number="INV-002", pending=False),
    ]


def test__payment_status_paid__remove_all_payments__is_unpaid() -> None:
    sut = make_sut()

    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.deleted_invoice(invoice_id=InvoiceId(1))

    assert sut.status() == IndividualPublicationPaymentStatus.Unpaid
    assert sut.payments() == []
