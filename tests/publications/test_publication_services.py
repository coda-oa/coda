from typing import cast

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.invoices import repository as invoice_repository
from coda.apps.publications.repositories import publication_repository
from coda.apps.publications.services import publications
from coda.contract import PublicationBilling
from coda.invoice import CreditorId, Invoice, InvoiceId
from coda.publication.publication import JournalId, Publication
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__unpaid_publication_without_invoice__payment_status_is_unpaid() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.save(contract)

    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal, contracts=(contract.in_first_year(),))
    publication.id = publication_repository.save(publication)

    payment_status = publications.get_payment_status(publication.id)

    assert payment_status == publications.PublicationUnpaid()


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
    invoice = pay_publication(publication)

    payment_status = publications.get_payment_status(publication.id)

    expected = publications.PublicationPaid(
        invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number
    )

    assert payment_status == expected


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__unpaid_publication_with_received_invoice__payment_status_is_unpaid_with_invoice() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.save(contract)

    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal, contracts=(contract.in_first_year(),))
    publication.id = publication_repository.save(publication)
    invoice = create_invoice_for_publication(publication)

    payment_status = publications.get_payment_status(publication.id)

    assert payment_status == publications.PublicationUnpaid(
        invoice_id=invoice.id, invoice_number=invoice.number
    )


@pytest.mark.django_db
def test__contract_with_consolidated_publication_billing__payment_status_is_covered_by_contract() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Consolidated
    contract.id = contract_repository.save(contract)

    journal = JournalId(modelfactory.journal().id)
    contract_year = contract.in_first_year()
    publication = domainfactory.publication(journal, contracts=(contract_year,))
    publication.id = publication_repository.save(publication)

    payment_status = publications.get_payment_status(publication.id)

    assert payment_status == publications.PublicationCoveredByContract(
        contract_id=contract.id,
        contract_name=contract_year.name,
        contract_year=contract_year.year,
    )


def pay_publication(publication: Publication) -> Invoice:
    invoice = create_invoice_for_publication(publication)
    invoice.pay()
    invoice.id = invoice_repository.save(invoice)
    return invoice


def create_invoice_for_publication(publication: Publication) -> Invoice:
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().id),
        positions=[domainfactory.publication_position(publication.id)],
    )
    invoice.reset_payment()

    invoice.id = invoice_repository.save(invoice)
    return invoice
