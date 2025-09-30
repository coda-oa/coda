import pytest
from coda.domain.invoice import InvoiceId
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import PublicationPayments, Payment


def make_sut() -> PublicationPayments:
    return PublicationPayments(publication_id=PublicationId(1))


def test__publication_payment_status__without_payments__no_payments_all_paid() -> None:
    sut = make_sut()

    assert_all_paid(sut)
    assert sut.payments() == []


def test__publication_payment_status__add_invoice_received__is_unpaid_with_pending_payment() -> (
    None
):
    sut = make_sut()

    sut.received_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")

    assert_all_payments_pending(sut)
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=True)
    ]


def test__publication_payment_status__add_paid__is_paid() -> None:
    sut = make_sut()

    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")

    assert_all_paid(sut)
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=False)
    ]


def test__payment_status_with_pending_payment__add_paid_for_same_invoice__is_paid_with_only_single_payment() -> (
    None
):
    sut = make_sut()

    sut.received_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")

    assert_all_paid(sut)
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=False)
    ]


def test__payment_status_with_pending_and_paid_payments_of_different_invoices__is_partially_paid() -> (
    None
):
    sut = make_sut()

    sut.received_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.paid_invoice(invoice_id=InvoiceId(2), invoice_number="INV-002")

    assert_payments_partially_paid(sut)
    assert sut.payments() == [
        Payment(invoice_id=InvoiceId(1), invoice_number="INV-001", pending=True),
        Payment(invoice_id=InvoiceId(2), invoice_number="INV-002", pending=False),
    ]


def test__payment_status_paid__remove_all_payments__is_unpaid() -> None:
    sut = make_sut()

    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.deleted_invoice(invoice_id=InvoiceId(1))

    assert_all_paid(sut)
    assert sut.payments() == []


def test__payment_status_with_paid_payment__reset_payment__has_pending_payments() -> None:
    sut = make_sut()

    sut.paid_invoice(invoice_id=InvoiceId(1), invoice_number="INV-001")
    sut.reset_payment(invoice_id=InvoiceId(1))

    assert_all_payments_pending(sut)


def test__empty_payment_status__reset_payment__raises_error() -> None:
    sut = make_sut()

    with pytest.raises(ValueError):
        sut.reset_payment(InvoiceId(1))


def test__empty_payment_status__invoice_deleted__raises_error() -> None:
    sut = make_sut()

    with pytest.raises(ValueError):
        sut.deleted_invoice(InvoiceId(1))


def assert_all_paid(sut: PublicationPayments) -> None:
    assert sut.all_paid()
    assert not sut.partially_paid()
    assert not sut.has_pending_payments()


def assert_all_payments_pending(sut: PublicationPayments) -> None:
    assert not sut.all_paid()
    assert not sut.partially_paid()
    assert sut.has_pending_payments()


def assert_payments_partially_paid(sut: PublicationPayments) -> None:
    assert not sut.all_paid()
    assert sut.has_pending_payments()
    assert sut.partially_paid()
