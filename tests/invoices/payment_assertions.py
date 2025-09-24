from collections.abc import Callable

from coda.domain.invoice import Invoice
from coda.domain.publication.payment import PublicationPayments, Payment

type PaymentAssertion = Callable[[PublicationPayments], None]
type CreatePaymentsAssertion = Callable[[Invoice], PaymentAssertion]


def new_invoice_paid_assertion(invoice: Invoice) -> PaymentAssertion:
    def expectation(actual: PublicationPayments) -> None:
        assert invoice.id is not None
        assert actual.all_paid()
        assert actual.payments() == [Payment(invoice.id, invoice.number, pending=False)]

    return expectation


def new_invoice_received_assertion(invoice: Invoice) -> PaymentAssertion:
    def expectation(actual: PublicationPayments) -> None:
        assert invoice.id is not None
        assert actual.has_pending_payments()
        assert actual.payments() == [Payment(invoice.id, invoice.number, pending=True)]

    return expectation
