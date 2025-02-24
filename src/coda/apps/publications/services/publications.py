from dataclasses import dataclass
from typing import cast

from coda.apps.invoices import repository as invoice_repository
from coda.apps.publications.repositories import publication_repository
from coda.contract import ContractId, ContractYear
from coda.invoice import InvoiceId
from coda.publication import BasePublication, PublicationId


@dataclass(slots=True)
class PublicationUnpaid:
    invoice_id: InvoiceId | None = None
    invoice_number: str = ""

    @property
    def status(self) -> str:
        return "Unpaid"

    def __str__(self) -> str:
        return self.status


@dataclass(slots=True)
class PublicationPaid:
    invoice_id: InvoiceId
    invoice_number: str

    @property
    def status(self) -> str:
        return "Paid"

    def __str__(self) -> str:
        return self.status


@dataclass(slots=True)
class PublicationCoveredByContract:
    contract_id: ContractId
    contract_name: str
    contract_year: int

    @property
    def status(self) -> str:
        return "Covered by contract"

    def __str__(self) -> str:
        return self.status


PublicationPaymentStatus = PublicationCoveredByContract | PublicationUnpaid | PublicationPaid


def get_payment_status(id: PublicationId) -> PublicationPaymentStatus:
    publication = publication_repository.get_by_id(id)
    consolidated_billing = consolidated_billing_contract(publication)
    if consolidated_billing:
        return PublicationCoveredByContract(
            contract_id=cast(ContractId, consolidated_billing.contract.id),
            contract_name=consolidated_billing.name,
            contract_year=consolidated_billing.year,
        )

    invoice = invoice_repository.invoice_with_publication(id)
    if invoice and invoice.is_paid():
        return PublicationPaid(
            invoice_id=cast(InvoiceId, invoice.id),
            invoice_number=invoice.number,
        )

    invoice_id = invoice.id if invoice else None
    invoice_number = invoice.number if invoice else ""
    return PublicationUnpaid(invoice_id=invoice_id, invoice_number=invoice_number)


def consolidated_billing_contract(publication: BasePublication) -> ContractYear | None:
    return next(
        (
            contract_year
            for contract_year in publication.contracts
            if contract_year.uses_consolidated_billing()
        ),
        None,
    )
