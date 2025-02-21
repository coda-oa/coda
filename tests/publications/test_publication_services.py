import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.invoices import repository as invoice_repository
from coda.apps.publications.repositories import publication_repository
from coda.apps.publications.services import publications
from coda.contract import PublicationBilling
from coda.invoice import CreditorId
from coda.publication.publication import JournalId, Publication
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__unpaid_publication__payment_status_is_unpaid() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.save(contract)

    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal, contracts=(contract.in_first_year(),))
    publication.id = publication_repository.save(publication)

    payment_status = publications.get_payment_status(publication.id)

    assert payment_status == publications.PublicationPaymentStatus.Unpaid


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__paid_publication__payment_status_is_paid() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.save(contract)

    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal, contracts=(contract.in_first_year(),))
    publication.id = publication_repository.save(publication)
    pay_publication(publication)

    payment_status = publications.get_payment_status(publication.id)

    assert payment_status == publications.PublicationPaymentStatus.Paid


@pytest.mark.django_db
def test__contract_with_consolidated_publication_billing__payment_status_is_covered_by_contract() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Consolidated
    contract.id = contract_repository.save(contract)

    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal, contracts=(contract.in_first_year(),))
    publication.id = publication_repository.save(publication)

    payment_status = publications.get_payment_status(publication.id)

    assert payment_status == publications.PublicationPaymentStatus.CoveredByContract


def pay_publication(publication: Publication) -> None:
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().id),
        positions=[domainfactory.publication_position(publication.id)],
    )
    invoice.pay()
    invoice_repository.save(invoice)
