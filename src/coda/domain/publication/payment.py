import enum
from dataclasses import dataclass

from coda.domain.contract import ContractId
from coda.domain.invoice import InvoiceId
from coda.domain.publication.publication import PublicationId


@dataclass(frozen=True, slots=True)
class PublicationUnpaid:
    pass


@dataclass(frozen=True, slots=True)
class InvoiceReceived:
    invoice_id: InvoiceId
    invoice_number: str


@dataclass(frozen=True, slots=True)
class PublicationPaid:
    invoice_id: InvoiceId
    invoice_number: str


@dataclass(frozen=True, slots=True)
class PublicationCoveredByContract:
    contract_id: ContractId
    contract_name: str
    contract_year: int


@dataclass(frozen=True, slots=True)
class Payment:
    invoice_id: InvoiceId
    invoice_number: str
    pending: bool


class IndividualPublicationPaymentStatus(enum.Enum):
    Unpaid = "unpaid"
    PartiallyPaid = "partially paid"
    Paid = "paid"

    def __str__(self) -> str:
        return self.value


class IndividualBillingPaymentStatus:
    """
    Represents the payment status of a publication that is billed individually (not covered by a contract).
    """

    def __init__(self, publication_id: PublicationId) -> None:
        self._publication_id = publication_id
        self._payments: dict[InvoiceId, Payment] = {}

    @property
    def publication_id(self) -> PublicationId:
        return self._publication_id

    def paid_invoice(self, invoice_id: InvoiceId, invoice_number: str) -> None:
        self._payments[invoice_id] = Payment(
            invoice_id=invoice_id, invoice_number=invoice_number, pending=False
        )

    def received_invoice(self, invoice_id: InvoiceId, invoice_number: str) -> None:
        self._payments[invoice_id] = Payment(
            invoice_id=invoice_id, invoice_number=invoice_number, pending=True
        )

    def deleted_invoice(self, invoice_id: InvoiceId) -> None:
        self._payments.pop(invoice_id, None)

    def _is_paid(self) -> bool:
        if not self._payments:
            return False

        return all(not payment.pending for payment in self._payments.values())

    def _all_pending(self) -> bool:
        return all(payment.pending for payment in self._payments.values())

    def status(self) -> IndividualPublicationPaymentStatus:
        if not self._payments or self._all_pending():
            return IndividualPublicationPaymentStatus.Unpaid

        if self._is_paid():
            return IndividualPublicationPaymentStatus.Paid

        return IndividualPublicationPaymentStatus.PartiallyPaid

    def payments(self) -> list[Payment]:
        return list(self._payments.values())


PublicationPayment = InvoiceReceived | PublicationPaid
PublicationPaymentStatus = PublicationCoveredByContract | IndividualBillingPaymentStatus
