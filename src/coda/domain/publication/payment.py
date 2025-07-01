from dataclasses import dataclass

from coda.domain.contract import ContractId
from coda.domain.invoice import InvoiceId


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


PublicationPayment = InvoiceReceived | PublicationPaid
PublicationPaymentStatus = (
    PublicationCoveredByContract | PublicationUnpaid | InvoiceReceived | PublicationPaid
)
