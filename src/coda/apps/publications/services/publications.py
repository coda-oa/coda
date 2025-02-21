import enum
import re

from coda.apps.invoices import repository as invoice_repository
from coda.apps.publications.repositories import publication_repository
from coda.publication.publication import PublicationId


class PublicationPaymentStatus(enum.StrEnum):
    Paid = enum.auto()
    Unpaid = enum.auto()
    CoveredByContract = enum.auto()

    def __str__(self) -> str:
        return " ".join(word for word in re.findall(r"[A-Z][a-z]*", self.name))


def get_payment_status(id: PublicationId) -> PublicationPaymentStatus:
    publication = publication_repository.get_by_id(id)
    if any(contract_year.uses_consolidated_billing() for contract_year in publication.contracts):
        return PublicationPaymentStatus.CoveredByContract

    if invoice_repository.publication_paid(id):
        return PublicationPaymentStatus.Paid

    return PublicationPaymentStatus.Unpaid
